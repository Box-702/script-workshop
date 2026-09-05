// =====================================================================
// stores/app.js —— 全局状态 + 业务动作（单例 store）
//
// 用 Vue 的 reactive() 做轻量状态管理，不引入 Pinia，保持依赖极简。
// 组件只负责渲染与交互，所有数据请求/流转都收敛到本文件的导出函数。
// =====================================================================

import { reactive } from 'vue'
import { api, importProject, streamChat } from '../api'
import { keyedDiff } from '../utils/diff'

/** 新对话里的欢迎语（Markdown）。 */
export const WELCOME_MD = `你好，我是剧本工坊的改编 Agent 👋

**开始方式**
- 点右上角 **＋ 新建剧本**：上传 \`.txt/.md/.docx\` 或粘贴原文，创建项目并自动分析你的写作风格、注入同类剧本知识；
- 在本对话里说 **生成初稿**，产出结构化剧本；
- 说 **把对白改口语一点 / 节奏改紧凑** 等，我会给出可逐条审阅的改动卡片；
- 问 **这类悬疑剧怎么设计反转？**，我检索项目知识库回答；
- 说 **记住：我喜欢冷峻、留白的风格**，我记入项目知识库。

左侧每个剧本项目下可新建多个**独立对话**，各自控制上下文，互不干扰。`

/** 知识库类型 -> 中文名。 */
export const KIND_NAME = {
  source: '原著原文',
  plot_direction: '同类剧本的可能走向',
  technique: '同类剧本的写作手法',
  author_style: '作者的语言风格',
}

// ---------------------------------------------------------------------
// 全局响应式状态
// ---------------------------------------------------------------------
export const store = reactive({
  // 当前选中的项目 / 对话
  pid: null,
  convId: null,

  // 项目树数据
  projects: [],        // 项目列表 [{ id, title, version_count }]
  convMap: {},         // pid -> 对话列表（懒加载缓存）
  expanded: {},        // pid -> 是否展开

  // 对话与版本
  messages: [],        // 当前对话消息 [{ role, content, events, payloads, streaming }]
  versions: [],        // 当前项目的版本列表

  // 顶栏状态徽章（/api/status 结果）
  status: null,
  statusLoading: true,

  // 右侧查看面板
  view: 'text',        // text | notes | knowledge | files | diff
  viewerText: '',      // 最新版本剧本全文（纯文本，供复制）
  viewerScript: null,  // 最新版本结构化剧本（供剧本排版渲染）
  viewerNotes: '',     // 编剧圣经 / 设定备忘（自由文本）
  projectFiles: null,  // 项目本地文件 { persist, root, folders }
  openFile: null,      // 当前打开的本地文本文件 { name, content }
  knowledge: [],       // [{ kind, docs }] 按类型分组
  diff: [],            // keyedDiff 结果
  diffMeta: '',        // “旧版本 → 新版本”说明文字

  // 杂项标记
  streaming: false,            // 是否正在流式生成
  checked: reactive(new Map()), // runId -> Set(已勾选 patch 下标)
  showNewProject: false,        // 新建剧本弹窗开关
  showWorkspace: false,         // 工作目录设置弹窗开关
  hint: '',                     // 输入区下方提示文字
  workspace: null,              // 当前工作目录信息 { root, configured, exists }
  toast: null,                  // 非阻塞通知 { id, message, type }

  // 改编提议审阅抽屉（对话里只显示摘要，细节在抽屉里看）
  drawer: { open: false, payload: null },
})

// ---------------------------------------------------------------------
// 非阻塞通知（替代 alert()：不打断、自动消失、可点关闭）
// ---------------------------------------------------------------------
let _toastTimer = null
export function notify(message, type = 'error') {
  store.toast = { id: Date.now(), message, type }
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => { store.toast = null }, 3800)
}
export function dismissToast() {
  clearTimeout(_toastTimer)
  store.toast = null
}

// ---------------------------------------------------------------------
// 导航时序守卫：快速切换项目/对话时，慢响应不得覆盖新选中的数据。
// 每次导航（选项目/选对话）取一个自增 token，await 返回后 token 已过期
// 就直接丢弃本次结果。
// ---------------------------------------------------------------------
let _navSeq = 0
function _isCurrent(token) { return token === _navSeq }

/** 删除项目及其所有对话、版本。 */
export async function deleteProject(pid) {
  try {
    await api(`/projects/${pid}`, 'DELETE')
    // 清除本地状态
    if (store.pid === pid) { store.pid = null; store.convId = null; store.messages = [] }
    delete store.convMap[pid]
    delete store.expanded[pid]
    await loadTree()
    notify('已删除项目', 'ok')
  } catch (e) { notify('删除失败：' + e.message) }
}

// ---------------------------------------------------------------------
// 顶栏状态徽章
// ---------------------------------------------------------------------
export async function loadStatus() {
  try { store.status = await api('/status') } catch (e) { store.status = { error: e.message } }
  finally { store.statusLoading = false }
}

// ---------------------------------------------------------------------
// 项目树（项目 -> 对话）
// ---------------------------------------------------------------------
/** 拉取项目列表；当前项目保持展开并刷新其对话。 */
export async function loadTree() {
  try {
    store.projects = await api('/projects')
  } catch (e) {
    notify('加载项目列表失败：' + e.message)
    return
  }
  // 当前选中项目保证处于展开态并加载对话
  if (store.pid && store.expanded[store.pid] !== false) {
    store.expanded[store.pid] = true
    await loadConversations(store.pid)
  }
}

/** 展开时懒加载某项目下的对话列表。 */
export async function loadConversations(pid) {
  try { store.convMap[pid] = await api(`/projects/${pid}/conversations`) } catch { store.convMap[pid] = [] }
}

/** 折叠/展开项目节点。 */
export async function toggleProject(pid) {
  store.expanded[pid] = !store.expanded[pid]
  if (store.expanded[pid]) await loadConversations(pid)
}

/** 选中项目：重置对话选择，自动选第一个对话，刷新右侧面板。 */
export async function selectProject(pid) {
  const token = ++_navSeq
  // 中止进行中的流式回复：流属于旧会话，继续写只会产生孤儿数据。
  if (_streamAbort) _streamAbort.abort()
  store.pid = pid
  store.convId = null
  store.expanded[pid] = true
  store.messages = [] // 先清空旧内容，避免等待期间显示上一个项目的消息
  await loadConversations(pid)
  if (!_isCurrent(token)) return
  const convs = store.convMap[pid] || []
  if (convs.length) await selectConversation(pid, convs[0].id, token)
  else {
    store.hint = '已选择剧本项目。可新建对话，或直接在下方对话里提出改编需求。'
    await loadViewer(token)
  }
}

/** 选中对话：加载历史消息并刷新右侧面板。token 沿用发起导航时的值。 */
export async function selectConversation(pid, convId, token = ++_navSeq) {
  _navSeq = token
  if (_streamAbort) _streamAbort.abort()
  store.pid = pid
  store.convId = convId
  store.hint = '对话已切换（每个对话独立上下文）。'
  store.messages = [] // 先清空旧对话内容，避免等待期间/失败时残留造成「串话」
  await loadHistory(token)
  if (!_isCurrent(token)) return
  await loadViewer(token)
}

/** 新建对话（自动命名，不弹窗）。若当前项目已有空白对话则直接选中，不重复创建。 */
export async function newConversation(pid) {
  // 检查是否有空白对话（无用户消息的对话）
  const convs = store.convMap[pid] || []
  for (const c of convs) {
    try {
      const msgs = await api(`/conversations/${c.id}/messages`)
      // 只有欢迎语（0 条用户消息）的对话视为空白
      const hasUserMsg = msgs.some((m) => m.role === 'user')
      if (!hasUserMsg) {
        store.hint = '当前已有空白对话，直接使用即可。'
        await selectConversation(pid, c.id)
        return
      }
    } catch { /* 查询失败继续 */ }
  }
  // 没有空白对话才真正创建
  const count = convs.length
  try {
    const c = await api(`/projects/${pid}/conversations`, 'POST', { title: `对话 ${count + 1}` })
    await loadConversations(pid) // 刷新左侧树的对话列表
    await selectConversation(pid, c.id)
  } catch (e) { notify('新建对话失败：' + e.message) }
}

/** 重命名对话（由树节点内联编辑提交）。pid 为该对话所属项目，刷新其对话列表。 */
export async function setConversationTitle(pid, convId, title) {
  const t = title.trim()
  if (!t) return
  try {
    await api(`/conversations/${convId}`, 'PATCH', { title: t })
    await loadConversations(pid || store.pid)
  } catch (e) { notify(e.message) }
}

/** 删除对话；若删的是当前对话则清空选择并回到项目空态。确认由调用方（内联两步）负责。
 *  pid 为该对话所属项目：从树上看可能不是当前选中的项目，刷新时不能混用 store.pid。 */
export async function deleteConversation(convId, pid = store.pid) {
  try {
    await api(`/conversations/${convId}`, 'DELETE')
    if (store.convId === convId) {
      store.convId = null
      store.messages = []
    }
    const target = pid || store.pid
    if (target) await loadConversations(target)
    notify('已删除对话', 'ok')
  } catch (e) { notify(e.message) }
}

// ---------------------------------------------------------------------
// 对话历史
// ---------------------------------------------------------------------
/** 拉取对话的历史消息；token 过期（用户已切走）时不写入，避免旧响应覆盖新会话。 */
export async function loadHistory(token = _navSeq) {
  let messages = []
  if (store.convId) {
    try { messages = await api(`/conversations/${store.convId}/messages`) } catch { messages = [] }
  }
  if (!_isCurrent(token)) return
  store.messages = messages.map((m) => ({
    role: m.role, content: m.content,
    events: m.events || [], payloads: m.payloads || [], streaming: false,
  }))
}

// ---------------------------------------------------------------------
// 右侧查看面板
// ---------------------------------------------------------------------
/** 加载最新版本全文 + 结构化剧本 + 知识库；token 过期时不写入。 */
export async function loadViewer(token = _navSeq) {
  if (!store.pid) { store.viewerText = ''; store.viewerScript = null; return }
  try {
    const versions = await api(`/projects/${store.pid}/versions`)
    if (!_isCurrent(token)) return
    store.versions = versions
    if (versions.length) {
      const t = await api(`/versions/${versions[0].id}/text`)
      if (!_isCurrent(token)) return
      store.viewerText = t.text
      try {
        const full = await api(`/versions/${versions[0].id}`)
        if (!_isCurrent(token)) return
        store.viewerScript = full.script || null
      } catch { store.viewerScript = null }
    } else {
      store.viewerText = ''
      store.viewerScript = null
    }
    await loadKnowledge()
    await loadNotes()
  } catch (e) {
    if (!_isCurrent(token)) return
    // 错误只进提示，不写进剧本文本字段（会被当成正文渲染、复制、导出）。
    store.viewerScript = null
    notify('剧本内容加载失败：' + e.message)
  }
}

/** 拉取编剧圣经 / 设定备忘。 */
export async function loadNotes() {
  if (!store.pid) { store.viewerNotes = ''; return }
  try { const r = await api(`/projects/${store.pid}/notes`); store.viewerNotes = r.notes || '' } catch { /* 保留 */ }
}

/** 保存编剧圣经 / 设定备忘；同步写入工作目录 04_知识库。 */
export async function saveNotes() {
  if (!store.pid) return
  await api(`/projects/${store.pid}/notes`, 'PUT', { notes: store.viewerNotes })
}

/** 拉取项目知识库并按类型分组。 */
export async function loadKnowledge() {
  if (!store.pid) return
  try {
    const r = await api(`/projects/${store.pid}/knowledge`)
    const groups = {}
    for (const d of r.docs || []) (groups[d.kind] = groups[d.kind] || []).push(d)
    store.knowledge = Object.keys(groups).map((k) => ({ kind: k, docs: groups[k] }))
  } catch { store.knowledge = [] }
}

/** 版本对比：最新版本 vs 上一版本。 */
export async function loadDiff() {
  if (!store.pid || store.versions.length < 1) { store.diff = []; store.diffMeta = ''; return }
  const vid = store.versions[0].id
  const fromId = store.versions.length > 1 ? store.versions[1].id : null
  try {
    const to = await api(`/versions/${vid}`)
    const from = fromId ? await api(`/versions/${fromId}`) : { script: { scenes: [], characters: [], locations: [] } }
    store.diff = keyedDiff(from.script, to.script)
    store.diffMeta = `${fromId || '（空）'} → ${vid}`
  } catch (e) { store.diff = []; store.diffMeta = `对比失败：${e.message}` }
}

/** 切换查看面板 tab；切到「版本对比」时按需加载。 */
export async function showView(name) {
  store.view = name
  if (name === 'diff') await loadDiff()
  if (name === 'files') await loadProjectFiles()
}

// ---------------------------------------------------------------------
// 本地剧本文件（查看 / 下载）
// ---------------------------------------------------------------------
function fileUrl(relpath) {
  const seg = String(relpath).split('/').map(encodeURIComponent).join('/')
  return `/api/projects/${store.pid}/files/${seg}`
}

/** 拉取当前项目的本地文件清单（按 01原稿/02版本/03导出/04知识库 分组）。 */
export async function loadProjectFiles() {
  if (!store.pid) { store.projectFiles = null; return }
  try { store.projectFiles = await api(`/projects/${store.pid}/files`) } catch { store.projectFiles = null }
}

/** 打开一个本地文件：文本内联预览，二进制触发下载。 */
export async function openProjectFile(relpath, isText) {
  const url = fileUrl(relpath)
  if (isText) {
    const res = await fetch(url)
    if (!res.ok) { notify('打开失败：' + res.status); return }
    store.openFile = { name: relpath.split('/').pop(), content: await res.text() }
  } else {
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
}

/** 关闭当前打开的文本文件预览。 */
export function closeOpenFile() { store.openFile = null }

/** 直接下载一个本地文件。 */
export function downloadProjectFile(relpath) {
  const a = document.createElement('a')
  a.href = fileUrl(relpath)
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

// ---------------------------------------------------------------------
// 导出剧本（.txt / .md / .docx）+ 工作目录
// ---------------------------------------------------------------------
const EXPORT_EXT = { txt: 'txt', md: 'md', docx: 'docx' }

/** 给版本打里程碑标记（draft/candidate/final / null 清除）。用于定稿管理。 */
export async function setVersionMilestone(versionId, milestone) {
  return api(`/versions/${versionId}/milestone`, 'POST', { milestone })
}

/** 把剧本编辑器的字段级改动应用到版本上，生成一个新的「手动编辑」版本。 */
export async function applyEdits(versionId, ops) {
  return api(`/versions/${versionId}/apply`, 'POST', { ops })
}

/** 触发浏览器下载某版本文本；成功后刷新工作目录（文件也会落盘到 03_导出）。 */
export async function exportVersion(versionId, fmt) {
  fmt = EXPORT_EXT[fmt] || 'txt'
  const res = await fetch(`/api/versions/${versionId}/export?fmt=${fmt}`)
  if (!res.ok) {
    const j = await res.json().catch(() => ({}))
    throw new Error(j.detail || res.statusText)
  }
  const disp = res.headers.get('Content-Disposition') || ''
  let filename = `剧本.${fmt}`
  // 优先取 RFC 5987 的 filename*（保留中文名），退回 ASCII filename。
  const star = disp.match(/filename\*=UTF-8''([^;]+)/i)
  if (star) {
    try { filename = decodeURIComponent(star[1]) } catch { filename = star[1] }
  } else {
    const m = disp.match(/filename="?([^";]+)"?/)
    if (m) filename = m[1]
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
  await loadWorkspace() // 导出后工作目录里多了 03_导出 文件
}

/** 拉取当前工作目录配置。 */
export async function loadWorkspace() {
  try { store.workspace = await api('/workspace') } catch { store.workspace = null }
}

/** 设置工作目录根路径与落盘模式；成功后刷新配置与右侧面板。persist=false 表示仅应用内、不落盘。 */
export async function setWorkspace(root, persist = true) {
  const r = await api('/workspace', 'POST', { root: root || '', persist })
  store.workspace = r
  await loadViewer()
}

/** 弹出系统原生文件夹选择对话框（Windows）；选择即设为工作目录。返回选中的路径。
 *  用户取消或弹出失败时返回 null（失败会抛出 Error，由调用方提示手动输入）。 */
export async function selectWorkspaceDirectory() {
  const r = await api('/workspace/select')
  if (r.cancelled) return null
  store.workspace = r
  await loadViewer()
  return r.path
}

/** 把当前项目落盘到工作目录（原稿 + 最新版本），返回目录树文本。 */
export async function syncProjectToWorkspace() {
  if (!store.pid) throw new Error('请先选择项目')
  const r = await api(`/projects/${store.pid}/structure`, 'POST')
  await loadWorkspace()
  return r.structure || ''
}

// ---------------------------------------------------------------------
// 发送消息（SSE 流式）
// ---------------------------------------------------------------------
/** 进行中的流式请求控制器：切换项目/对话时中止，避免流写进已离开的会话。 */
let _streamAbort = null

/** 发送一条用户消息，流式接收回复并实时更新最后一条 assistant 消息。 */
export async function sendMessage(text) {
  if (store.streaming || !text) return
  // 先渲染用户气泡 + 一个「打字中」的 assistant 气泡
  store.messages.push({ role: 'user', content: text, events: [], payloads: [], streaming: false })
  const reply = reactive({ role: 'assistant', content: '', events: [], payloads: [], streaming: true })
  store.messages.push(reply)

  store.streaming = true
  _streamAbort = new AbortController()
  try {
    await streamChat(
      { project_id: store.pid, conversation_id: store.convId, message: text, meta: null },
      (ev) => handleStreamEvent(ev, reply),
      _streamAbort.signal,
    )
  } catch (e) {
    // 主动切走会话导致的中止不算错误，保留已收到的部分内容即可。
    if (e && e.name !== 'AbortError') reply.content = `请求失败：${e.message}`
  } finally {
    _streamAbort = null
    reply.streaming = false
    store.streaming = false
    await loadTree()
  }
}

/** 处理单帧 SSE 事件，更新回复消息对象。 */
function handleStreamEvent(ev, reply) {
  if (ev.event === 'tool_call' || ev.event === 'tool_result') {
    reply.events.push(ev.data)
  } else if (ev.event === 'token') {
    reply.content += ev.data.delta
  } else if (ev.event === 'done') {
    reply.content = ev.data.reply || reply.content
    reply.payloads = ev.data.payloads || []
    afterAgentDone(ev.data)
  } else if (ev.event === 'error') {
    reply.content = `出错：${ev.data.message}`
  }
}

/** done 事件后的收尾：首轮对话时挂上项目/对话，并刷新右侧面板。 */
async function afterAgentDone(data) {
  if (data.project_id && !store.pid) {
    store.pid = data.project_id
    store.convId = data.thread_id || store.convId
    store.expanded[store.pid] = true
    await loadConversations(store.pid)
    await loadTree()
  }
  if (store.pid) await loadViewer()
}

// ---------------------------------------------------------------------
// 审阅动作（接受 / 拒绝 / 重新生成 / 编辑 patch）
// ---------------------------------------------------------------------
/** 勾选/取消某个 patch 操作。 */
export function toggleCheck(runId, i) {
  const set = store.checked.get(runId) || new Set()
  set.has(i) ? set.delete(i) : set.add(i)
  store.checked.set(runId, set)
}

/** 打开/关闭审阅详情抽屉（payload 为 patch_review 消息载荷）。 */
export function openPatchDrawer(payload) {
  store.drawer.payload = payload
  store.drawer.open = true
}
export function closePatchDrawer() {
  store.drawer.open = false
}

/** 向后端恢复审阅流程（resume）；完成后关闭抽屉并刷新右侧面板。 */
export async function resumeReview(runId, action, opts = {}) {
  if (store.streaming) return
  // 在对话里补一条用户操作记录 + 打字中气泡
  const summary = action === 'accept'
    ? (opts.patch_indexes?.length ? `接受改编提议（勾选 ${opts.patch_indexes.length} 项）` : '接受全部改编提议')
    : action === 'reject' ? '拒绝这次改编提议'
    : action === 'regenerate' ? `重新生成（反馈：${opts.feedback || '换个思路'}）`
    : '编辑 patch 后接受'
  store.messages.push({ role: 'user', content: summary, events: [], payloads: [], streaming: false })
  const reply = reactive({ role: 'assistant', content: '', events: [], payloads: [], streaming: true })
  store.messages.push(reply)

  store.streaming = true
  const meta = { intent: 'resume', run_id: runId, action, patch_indexes: opts.patch_indexes ?? null, feedback: opts.feedback ?? null, patch: opts.patch ?? null }
  try {
    const r = await api('/chat', 'POST', { project_id: store.pid, conversation_id: store.convId, message: '', meta })
    reply.content = r.reply
    reply.events = r.events || []
    reply.payloads = r.payloads || []
    await loadViewer()
  } catch (e) {
    reply.content = '操作失败：' + e.message
  } finally {
    reply.streaming = false
    store.streaming = false
    store.drawer.open = false
  }
}

// ---------------------------------------------------------------------
// 新建剧本（导入项目）
// ---------------------------------------------------------------------
/** 提交新建剧本表单；成功后选中新项目（及其首个对话）。 */
export async function submitNewProject({ title, adapt, file, raw }) {
  const fd = new FormData()
  fd.append('title', title)
  fd.append('adaptation_type', adapt)
  if (file) fd.append('file', file)
  else fd.append('raw_text', raw)
  const r = await importProject(fd)
  store.showNewProject = false
  await loadTree()
  await selectProject(r.id)
  if (r.conversation_id) await selectConversation(r.id, r.conversation_id)
  for (const w of r.warnings || []) notify(w)
}
