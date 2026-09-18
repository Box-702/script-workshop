// =====================================================================
// stores/app.js —— 全局状态 + 业务动作（单例 store）
//
// 用 Vue 的 reactive() 做轻量状态管理，不引入 Pinia，保持依赖极简。
// 组件只负责渲染与交互，所有数据请求/流转都收敛到本文件的导出函数。
// =====================================================================

import { reactive } from 'vue'
import { api, importProject, streamChat } from '../api'
import { keyedDiff } from '../utils/diff'

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
  scenesMap: {},       // pid -> 场景列表 [{id, title, characters, beats_count}]（懒加载）
  expanded: {},        // pid -> 是否展开

  // 全局对话（不绑定项目）
  globalConvs: [],     // [{ id, title, user_message_count, created_at }]
  // 工作区文件树
  workspaceTree: null, // { root, folders: [{name, type, children}] }
  // 左栏当前 tab
  leftTab: 'chat',     // 'chat' | 'workspace'

  // 对话与版本
  messages: [],        // 当前对话消息 [{ role, content, events, payloads, streaming }]
  versions: [],        // 当前项目的版本列表

  // 左侧面板开关（默认展开，记忆在 localStorage）
  leftOpen: true,
  // 场景聚焦模式（点击左侧场景时设置，右栏显示单个场景详情）
  focusedSceneId: null,
  // 右侧查看面板开关（默认收起，记忆在 localStorage）
  rightOpen: false,

  // 右侧查看面板
  view: 'text',        // text | notes | files | diff
  viewerText: '',      // 最新版本剧本全文（纯文本，供复制）
  viewerScript: null,  // 最新版本结构化剧本（供剧本排版渲染）
  viewerNotes: '',     // 编剧圣经 / 设定备忘（自由文本）
  notesDirty: false,   // 设定有未保存改动：切换项目时不被服务端内容覆盖
  projectFiles: null,  // 项目本地文件 { persist, root, folders }
  openFile: null,      // 当前打开的本地文本文件 { name, content }
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

  // 后台任务面板
  tasks: [],              // [{id, name, status, steps, result, created_at, finished_at}]

  // ---- v3.0 视频制作 ----
  // 镜头数据
  shots: [],              // 当前项目的镜头列表
  videoVersions: [],      // 视频版本列表
  videoVersionId: null,   // 当前镜头列表所属的视频版本
  videoJobs: [],          // 视频生成任务列表
  videoBatch: null,       // 批量生成批次状态（null/对象）
  videoMode: localStorage.getItem('sw_video_mode') || 'auto',   // 生成模式：auto | approval
  videoResolution: localStorage.getItem('sw_video_resolution') || '',  // 空=全局默认(768P)
  // 视频播放器
  playingVideo: null,     // { url, title, meta }
  // Prompt 编辑
  editingPrompt: null,    // 正在编辑的 shot 对象
  promptHistory: [],      // 当前镜头沿视频版本父链的审阅历史
  promptHistoryLoading: false,

  // 开始页建议卡片 -> 输入框的填充通道（draftSeq 变化触发 ChatComposer 取稿）
  draft: '',
  draftSeq: 0,
})

// ---------------------------------------------------------------------
// 非阻塞通知（替代 alert()：不打断、自动消失、可点关闭）
// ---------------------------------------------------------------------
let _toastTimer = null
let _taskRefreshTimer = null
let _taskRefreshSeq = 0
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
// 后台任务管理
// ---------------------------------------------------------------------
/** 从后端拉取后台任务列表（轮询用）。 */
export async function refreshTasks() {
  const seq = ++_taskRefreshSeq
  try {
    const tasks = await api('/tasks?active_only=false')
    if (seq !== _taskRefreshSeq) return
    store.tasks = tasks || []
  } catch { /* 静默 */ }
}

/** SSE 收到后台任务启动事件时，触发后端任务刷新。 */
export function onSubAgentStarted() {
  // 异步刷新，不阻塞消息流
  clearTimeout(_taskRefreshTimer)
  _taskRefreshTimer = setTimeout(() => {
    _taskRefreshTimer = null
    refreshTasks()
  }, 500)
}

/** 清除已完成的任务。 */
export function clearCompletedTasks() {
  store.tasks = store.tasks.filter((t) => t.status === 'running' || t.status === 'pending')
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
// 右侧查看面板开关
// ---------------------------------------------------------------------
/** 开/关左侧导航面板。 */
export function toggleLeftPanel() {
  store.leftOpen = !store.leftOpen
  localStorage.setItem('sw-layout:leftOpen', store.leftOpen ? '1' : '0')
}

/** 聚焦到单个场景（右栏显示场景详情）。传 null 退出聚焦。 */
export function focusScene(sceneId) {
  store.focusedSceneId = sceneId
  if (sceneId && !store.rightOpen) {
    store.rightOpen = true
    localStorage.setItem('sw-layout:rightOpen', '1')
  }
  if (sceneId) store.view = 'scene'
}
/** 开/右侧查看面板；偏好记忆在 localStorage（默认收起）。 */
export function toggleRightPanel() {
  store.rightOpen = !store.rightOpen
  localStorage.setItem('sw-layout:rightOpen', store.rightOpen ? '1' : '0')
}
/** 恢复上次的面板开关偏好（App 挂载时调用）。 */
export function restorePanelPrefs() {
  store.leftOpen = localStorage.getItem('sw-layout:leftOpen') !== '0'  // 默认开
  store.rightOpen = localStorage.getItem('sw-layout:rightOpen') === '1'  // 默认关
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
export async function loadConversations(pid, token = null) {
  try {
    const conversations = await api(`/projects/${pid}/conversations`)
    if (token !== null && !_isCurrent(token)) return
    store.convMap[pid] = conversations
  } catch {
    if (token === null || _isCurrent(token)) store.convMap[pid] = []
  }
}

/** 展开时懒加载某项目的场景列表（从最新版本提取）。 */
export async function loadScenes(pid) {
  try {
    const versions = await api(`/projects/${pid}/versions`)
    if (versions.length) {
      const v = await api(`/versions/${versions[0].id}`)
      const scenes = (v.script?.scenes || []).map((s) => ({
        id: s.id,
        title: s.title || s.id,
        characters: s.characters || [],
        beats_count: (s.beats || []).length,
        purpose: s.purpose || '',
      }))
      store.scenesMap[pid] = scenes
    } else {
      store.scenesMap[pid] = []
    }
  } catch { store.scenesMap[pid] = [] }
}

/** 折叠/展开项目节点。 */
export async function toggleProject(pid) {
  store.expanded[pid] = !store.expanded[pid]
  if (store.expanded[pid]) {
    await loadConversations(pid)
    await loadScenes(pid)
  }
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
  await loadConversations(pid, token)
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
  // 检查是否有空白对话（无用户消息的对话）——利用列表接口已返回的 user_message_count，无需逐个请求。
  const convs = store.convMap[pid] || []
  const blank = convs.find((c) => (c.user_message_count ?? 0) === 0)
  if (blank) {
    store.hint = '当前已有空白对话，直接使用即可。'
    await selectConversation(pid, blank.id)
    return
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
    else await loadGlobalConversations()
    notify('已删除对话', 'ok')
  } catch (e) { notify(e.message) }
}

// ---------------------------------------------------------------------
// 全局对话（不绑定项目）
// ---------------------------------------------------------------------

/** 加载全局对话列表。 */
export async function loadGlobalConversations() {
  try { store.globalConvs = await api('/conversations') } catch { store.globalConvs = [] }
}

/** 新建全局对话。 */
export async function newGlobalConversation() {
  const blank = store.globalConvs.find((c) => (c.user_message_count ?? 0) === 0)
  if (blank) {
    store.hint = '当前已有空白对话，直接使用即可。'
    await selectGlobalConversation(blank.id)
    return
  }
  const count = store.globalConvs.length
  try {
    const c = await api('/conversations', 'POST', { title: `对话 ${count + 1}` })
    await loadGlobalConversations()
    await selectGlobalConversation(c.id)
  } catch (e) { notify('新建对话失败：' + e.message) }
}

/** 选中一个全局对话（不关联项目）。 */
export async function selectGlobalConversation(convId) {
  const token = ++_navSeq
  store.pid = null
  store.convId = convId
  store.focusedSceneId = null
  store.messages = []
  store.versions = []
  await loadHistory(token)
}

// ---------------------------------------------------------------------
// 工作区文件树
// ---------------------------------------------------------------------

/** 加载工作区目录结构。 */
export async function loadWorkspaceTree() {
  try {
    const ws = await api('/workspace')
    if (!ws.configured || !ws.root) {
      store.workspaceTree = null
      return
    }
    // 加载根目录下的项目文件夹
    const folders = []
    for (const p of store.projects) {
      try {
        const files = await api(`/projects/${p.id}/files`)
        if (files.folders) {
          folders.push({ name: p.title, pid: p.id, folders: files.folders })
        }
      } catch {}
    }
    store.workspaceTree = { root: ws.root, folders }
  } catch {
    store.workspaceTree = null
  }
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
/** 加载最新版本全文 + 结构化剧本；token 过期时不写入。 */
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
  } catch (e) {
    if (!_isCurrent(token)) return
    store.viewerScript = null
    notify('剧本内容加载失败：' + e.message)
  }
}

/** 拉取编剧圣经 / 设定备忘。有未保存改动时不覆盖（否则切换项目会静默丢字）。 */
export async function loadNotes(token = _navSeq) {
  if (!store.pid) { store.viewerNotes = ''; return }
  try {
    const r = await api(`/projects/${store.pid}/notes`)
    if (!_isCurrent(token)) return
    if (store.notesDirty) {
      notify('有未保存的编剧设定改动，输入框内容已保留；确认后请保存或清空。', 'ok')
      return
    }
    store.viewerNotes = r.notes || ''
  } catch { /* 保留 */ }
}

/** 保存编剧圣经 / 设定备忘；同步写入工作目录 04_知识库。 */
export async function saveNotes() {
  if (!store.pid) return
  await api(`/projects/${store.pid}/notes`, 'PUT', { notes: store.viewerNotes })
  store.notesDirty = false
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

/** 切换查看面板 tab。 */
export async function showView(name) {
  store.view = name
  if (name === 'agents') await refreshTasks()
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
    // 后台任务启动时立即刷新任务列表
    if ((ev.data.payloads || []).some((p) => p.type === 'sub_agent_started')) {
      onSubAgentStarted()
    }
    afterAgentDone(ev.data)
  } else if (ev.event === 'error') {
    reply.content = `出错：${ev.data.message}`
  }
}

/** done 事件后的收尾：首轮对话时挂上项目/对话，并刷新右侧面板与后台任务。 */
async function afterAgentDone(data) {
  if (data.project_id && !store.pid) {
    store.pid = data.project_id
    store.convId = data.thread_id || store.convId
    store.expanded[store.pid] = true
    await loadConversations(store.pid)
    await loadTree()
  }
  if (store.pid) await loadViewer()
  // 刷新后台任务（任务可能已完成，也可能仍在运行）
  await refreshTasks()
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

// =====================================================================
// v3.0 视频制作相关函数
// =====================================================================

/** 加载项目的镜头列表（从最新 video version 读取）。 */
export async function loadShots() {
  if (!store.pid) {
    store.shots = []
    store.videoVersions = []
    store.videoVersionId = null
    return
  }
  try {
    const versions = await api(`/projects/${store.pid}/video-versions`)
    store.videoVersions = versions
    if (versions.length > 0) {
      const latest = await api(`/video-versions/${versions[0].id}`)
      store.videoVersionId = latest.id
      store.shots = latest.shots || []
    } else {
      store.shots = []
      store.videoVersionId = null
    }
  } catch {
    store.shots = []
    store.videoVersionId = null
  }
}

/** 加载当前镜头的 Prompt 审阅历史与版本差异。 */
export async function loadPromptHistory(shotId) {
  if (!store.pid || !store.videoVersionId || !shotId) {
    store.promptHistory = []
    return
  }
  store.promptHistoryLoading = true
  try {
    const data = await api(
      `/projects/${store.pid}/video-versions/${store.videoVersionId}/shots/${encodeURIComponent(shotId)}/prompt-history`,
    )
    store.promptHistory = data.history || []
  } catch {
    store.promptHistory = []
  } finally {
    store.promptHistoryLoading = false
  }
}

/** 加载项目的视频生成任务列表。 */
export async function loadVideoJobs() {
  if (!store.pid) { store.videoJobs = []; return }
  try {
    store.videoJobs = await api(`/projects/${store.pid}/video/jobs`)
  } catch { store.videoJobs = [] }
}

/** 提交视频生成任务。 */
export async function submitVideoJob(shot) {
  if (!store.pid || !shot?.video_prompt) return
  if (shot.prompt_status !== 'approved') {
    notify('请先编辑并批准这个镜头的 Prompt', 'info')
    openPromptEditor(shot)
    return
  }
  // 从已配置的 video providers 中选第一个
  let provider = 'kling'
  let model = 'kling-v3'
  try {
    const providers = await api('/providers?kind=video')
    const configured = providers.find(p => p.configured && p.enabled)
    if (configured) {
      provider = configured.name
      model = configured.config?.model || model
    }
  } catch {}

  try {
    const job = await api(`/projects/${store.pid}/video/generate`, 'POST', {
      shot_id: shot.id,
      provider,
      model,
      prompt: shot.video_prompt,
      version_id: store.videoVersionId,
    })
    notify(`视频任务已提交：${shot.subject || shot.id}`, 'ok')
    await loadVideoJobs()
    return job
  } catch (e) {
    notify(`提交失败：${e.message}`, 'error')
  }
}

/** 取消视频生成任务。 */
export async function cancelVideoJob(jobId) {
  try {
    await api(`/video/jobs/${jobId}/cancel`, 'POST')
    await loadVideoJobs()
  } catch (e) {
    notify(`取消失败：${e.message}`, 'error')
  }
}

/** 设置生成模式（持久化到本地，下次进入记住选择）。 */
export function setVideoMode(mode) {
  store.videoMode = mode
  localStorage.setItem('sw_video_mode', mode)
}

/** 设置分辨率覆盖（空串 = 跟随全局默认 768P）。 */
export function setVideoResolution(res) {
  store.videoResolution = res
  localStorage.setItem('sw_video_resolution', res)
}

/** 启动批量生成（自动/审批模式由 store.videoMode 决定）。 */
export async function startVideoBatch() {
  if (!store.pid) return
  const approved = store.shots.filter((shot) => shot.video_prompt && shot.prompt_status === 'approved')
  if (!approved.length) {
    notify('请先逐镜批准视频 Prompt，再开始批量生成', 'info')
    return
  }
  try {
    store.videoBatch = await api(`/projects/${store.pid}/video/generate-batch`, 'POST', {
      mode: store.videoMode,
      resolution: store.videoResolution || null,
    })
    notify(`批量生成已启动（${store.videoMode === 'auto' ? '自动' : '审批'}模式）`, 'ok')
    await loadVideoJobs()
  } catch (e) {
    notify(`批量生成启动失败：${e.message}`, 'error')
  }
}

/** 查询最新批次进度。 */
export async function pollVideoBatch() {
  if (!store.pid) return
  try {
    const b = await api(`/projects/${store.pid}/video/batch`)
    store.videoBatch = b.id ? b : null
    if (b.id && (b.status === 'running' || b.status === 'awaiting_approval')) await loadVideoJobs()
  } catch { /* 忽略轮询错误 */ }
}

/** 向批次下达命令：approve / reroll / abort。 */
export async function batchCommand(command) {
  const b = store.videoBatch
  if (!b?.id) return
  try {
    store.videoBatch = await api(`/video/batches/${b.id}/command`, 'POST', { command })
    const zh = { approve: '已放行下一镜', reroll: '正在重跑当前镜', abort: '批次已终止' }
    notify(zh[command] || '命令已执行', 'ok')
    await loadVideoJobs()
  } catch (e) {
    notify(`命令失败：${e.message}`, 'error')
  }
}

/** 重试视频生成任务。 */
export async function retryVideoJob(jobId) {
  try {
    await api(`/video/jobs/${jobId}/retry`, 'POST')
    await loadVideoJobs()
  } catch (e) {
    notify(`重试失败：${e.message}`, 'error')
  }
}

/** 打开视频播放器。 */
export function playVideo(shot) {
  if (shot?.video_url) {
    store.playingVideo = { url: shot.video_url, title: shot.subject || shot.id, meta: { provider: shot.video_job_id } }
  }
}

/** 关闭视频播放器。 */
export function closeVideo() {
  store.playingVideo = null
}

/** 打开 Prompt 编辑器。 */
export function openPromptEditor(shot) {
  store.editingPrompt = shot
  store.promptHistory = []
}

/** 关闭 Prompt 编辑器。 */
export function closePromptEditor() {
  store.editingPrompt = null
  store.promptHistory = []
}

/** 批量应用 Prompt 审阅决定，服务端会创建新的可回滚视频版本。 */
export async function bulkReviewPrompts(shotIds, decision = 'approve', note = '') {
  if (!store.pid || !store.videoVersionId || !shotIds?.length) return
  try {
    const result = await api(
      `/projects/${store.pid}/video-versions/${store.videoVersionId}/prompts/review`,
      'POST',
      { shot_ids: shotIds, decision, note },
    )
    await loadShots()
    notify(`已批量处理 ${result.reviewed_count} 个镜头`, 'ok')
    return result
  } catch (e) {
    notify(`批量审阅失败：${e.message}`, 'error')
    throw e
  }
}

/** 保存并审阅镜头 Prompt，服务端会创建新的可回滚视频版本。 */
export async function saveShotPrompt(shot, decision = 'save', note = '') {
  if (!store.pid || !shot || !store.videoVersionId) return
  try {
    await api(
      `/projects/${store.pid}/video-versions/${store.videoVersionId}/shots/${encodeURIComponent(shot.id)}/prompt`,
      'PUT',
      {
        prompt: shot.video_prompt,
        decision,
        note,
      },
    )
    await loadShots()
    const labels = {
      save: 'Prompt 草稿已保存',
      approve: 'Prompt 已批准，可以出片',
      needs_revision: '已标记为需要修改',
    }
    notify(labels[decision] || 'Prompt 已保存', 'ok')
    if (store.editingPrompt?.id === shot.id) closePromptEditor()
  } catch (e) {
    notify(`Prompt 保存失败：${e.message}`, 'error')
  }
}

/** 仅在当前界面需要手动刷新时调用，避免重复写入版本。 */
export async function refreshVideoWorkspace() {
  await Promise.all([loadShots(), loadVideoJobs()])
}
