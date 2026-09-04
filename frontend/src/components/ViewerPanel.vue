<script setup>
// =====================================================================
// ViewerPanel.vue —— 右侧文本查看面板
//
// 三个 tab：
//   - 剧本文本：以「标准剧本排版」渲染当前项目最新版本全文（可导出 txt/md/docx）；
//   - 知识库：按类型分组的项目知识条目；
//   - 版本对比：最新版本 vs 上一版本的差异列表。
// 空态均为教学式文案，告诉用户如何让内容出现。
// =====================================================================

import { computed, ref } from 'vue'
import ScreenplayView from './ScreenplayView.vue'
import ScreenplayEditor from './ScreenplayEditor.vue'
import FolderTree from './FolderTree.vue'
import FolderIcon from './FolderIcon.vue'
import { store, showView, KIND_NAME, exportVersion, syncProjectToWorkspace, setVersionMilestone, notify, loadViewer, saveNotes, openProjectFile, closeOpenFile, downloadProjectFile } from '../stores/app'
import { fmtVal } from '../utils/format'

const TABS = [
  { key: 'text', label: '剧本文本' },
  { key: 'notes', label: '编剧设定' },
  { key: 'knowledge', label: '知识库' },
  { key: 'files', label: '本地文件' },
  { key: 'diff', label: '版本对比' },
]
const currentTitle = computed(() => store.projects.find((p) => p.id === store.pid)?.title || '未选择项目')

const latestVersionId = computed(() => store.versions[0]?.id || null)
const latestMilestone = computed(() => store.versions[0]?.milestone || null)
const MILESTONE_ZH = { draft: '草稿', candidate: '候选', final: '终稿' }

/** 把当前版本定为终稿（并刷新右侧面板）。 */
async function markFinal() {
  if (!latestVersionId.value) return
  try {
    await setVersionMilestone(latestVersionId.value, 'final')
    await loadViewer()
    notify('已设为终稿', 'ok')
  } catch (e) { notify('设置失败：' + e.message) }
}

// ---- 复制剧本全文 ----
const copied = ref(false)
let copiedTimer = null
async function copyScript() {
  try {
    await navigator.clipboard.writeText(store.viewerText)
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copied.value = false), 1400)
  } catch { /* 剪贴板不可用时静默 */ }
}

// ---- 导出 ----
const exportOpen = ref(false)
const exporting = ref('')
const exportMsg = ref('')
async function doExport(fmt) {
  if (!latestVersionId.value) return
  exportOpen.value = false
  exporting.value = fmt
  exportMsg.value = ''
  try {
    await exportVersion(latestVersionId.value, fmt)
    exportMsg.value = `已导出 .${fmt}（同步到工作目录）`
  } catch (e) {
    exportMsg.value = '导出失败：' + e.message
  } finally {
    exporting.value = ''
  }
}

// ---- 同步到工作目录 ----
const syncing = ref(false)
const showWs = ref(false)
async function syncToWorkspace() {
  if (!store.pid) return
  syncing.value = true
  exportMsg.value = ''
  try {
    await syncProjectToWorkspace()
    showWs.value = true
    exportMsg.value = '已同步到工作目录'
  } catch (e) {
    exportMsg.value = e.message
  } finally {
    syncing.value = false
  }
}

/** diff 类型 -> 标签与配色。 */
function diffMeta(t) {
  return t === '+' ? { label: '＋ 新增', cls: 't-add' }
    : t === '-' ? { label: '－ 删除', cls: 't-del' }
    : { label: '～ 修改', cls: 't-mod' }
}

// ---- 本地文件 ----
function fmtSize(b) {
  if (!b && b !== 0) return ''
  return b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : (b / 1024).toFixed(1) + ' KB'
}
function isTextFile(name) { return /\.(txt|md|markdown)$/i.test(name) }
function fileMtime(t) {
  if (!t) return ''
  const d = new Date(t * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// ---- 内置剧本编辑器 ----
const editing = ref(false)
function onSaved() {
  editing.value = false
  loadViewer()
}

// ---- 编剧圣经 / 设定备忘 ----
const savingNotes = ref(false)
async function onSaveNotes() {
  if (savingNotes.value) return
  savingNotes.value = true
  try {
    await saveNotes()
    notify('已保存编剧设定', 'ok')
  } catch (e) { notify('保存失败：' + e.message) } finally { savingNotes.value = false }
}
</script>

<template>
  <div class="viewer">
    <!-- tab 头 -->
    <div class="v-head">
      <div class="v-tabs">
        <button
          v-for="t in TABS" :key="t.key"
          class="v-tab" :class="{ active: store.view === t.key }"
          @click="showView(t.key)"
        >{{ t.label }}</button>
      </div>
      <div class="vt">{{ currentTitle }}</div>
      <!-- 操作按钮：仅当有可操作的版本/文本时出现，并在出现/消失时平滑过渡，避免切换 tab 时突兀地弹出 -->
      <Transition name="vacts">
        <div v-if="store.view === 'text' && latestVersionId" class="v-acts">
          <button v-if="store.viewerScript && !editing" class="ghost small" @click="editing = true">✎ 编辑</button>
          <div class="export-wrap">
            <button class="ghost small" @click="exportOpen = !exportOpen">
              {{ exporting ? `导出中…` : '⤓ 导出' }}
            </button>
            <div v-if="exportOpen" class="export-menu">
              <button class="ghost small" @click="doExport('txt')">.txt 纯文本</button>
              <button class="ghost small" @click="doExport('md')">.md 文档</button>
              <button class="ghost small" @click="doExport('docx')">.docx Word</button>
            </div>
          </div>
          <button class="ghost small" :disabled="!store.viewerText" @click="copyScript">
            {{ copied ? '✓ 已复制' : '⧉ 复制' }}
          </button>
        </div>
      </Transition>
    </div>

    <!-- 各 tab 内容：切换时做平滑淡入淡出（out-in），避免硬切 -->
    <div class="v-body-wrap">
      <Transition name="tabfade" mode="out-in">
    <!-- 剧本文本：标准剧本排版 -->
    <div v-if="store.view === 'text'" class="v-body">
      <ScreenplayEditor
        v-if="editing && store.viewerScript"
        :script="store.viewerScript"
        :version-id="latestVersionId"
        @saved="onSaved"
        @cancel="editing = false"
      />
      <ScreenplayView v-else-if="store.viewerScript" :script="store.viewerScript" />
      <pre v-else-if="store.viewerText">{{ store.viewerText }}</pre>
      <div v-else class="v-empty">
        <template v-if="store.pid">还没有剧本版本。在左侧对话里说「生成初稿」，生成的内容会出现在这里。</template>
        <template v-else>选择剧本项目后，这里会以「剧本排版」显示当前剧本文本。</template>
      </div>

      <div v-if="store.pid && (store.viewerScript || store.viewerText)" class="v-foot">
        <div class="foot-bar">
          <span v-if="latestMilestone" class="mile" :class="'mile-' + latestMilestone" :title="'版本标记：' + (MILESTONE_ZH[latestMilestone] || latestMilestone)">
            {{ MILESTONE_ZH[latestMilestone] || latestMilestone }}
          </span>
          <button v-if="latestMilestone !== 'final'" class="ghost small" @click="markFinal">◆ 定为终稿</button>
          <button v-if="store.workspace?.configured" class="ghost small" :disabled="syncing" @click="syncToWorkspace">
            {{ syncing ? '同步中…' : '⤷ 同步到工作目录' }}
          </button>
          <button v-if="store.workspace?.configured" class="ghost small" @click="showWs = !showWs">
            {{ showWs ? '收起目录' : '目录结构' }}
          </button>
          <span v-if="exportMsg" class="foot-msg">{{ exportMsg }}</span>
        </div>
        <div v-if="store.workspace?.configured && showWs" class="foot-ws">
          <FolderTree :root="store.workspace.root" />
        </div>
      </div>
    </div>

    <!-- 编剧圣经 / 设定备忘 -->
    <div v-else-if="store.view === 'notes'" class="v-body">
      <div v-if="store.pid" class="notes-wrap">
        <div class="notes-hint">记录人物小传、时间线、伏笔清单等「剧本圣经」；这些作为你的创作设定随时可改。</div>
        <textarea
          v-model="store.viewerNotes"
          class="notes-ta"
          placeholder="例如：&#10;人物：林然（主角）——前刑警，寡言，怕火。&#10;时间线：1987 旧货市场失火 → 1997 重逢。&#10;伏笔：红雨衣、未寄出的照片。"
          spellcheck="false"
        ></textarea>
        <div class="notes-foot">
          <button class="small" :disabled="savingNotes" @click="onSaveNotes">{{ savingNotes ? '保存中…' : '保存设定' }}</button>
          <span class="notes-tip">会自动写入工作目录的 04_知识库</span>
        </div>
      </div>
      <div v-else class="v-empty">选择剧本项目后，这里可以维护你的「编剧圣经 / 设定」。</div>
    </div>

    <!-- 本地剧本文件 -->
    <div v-else-if="store.view === 'files'" class="v-body">
      <!-- 打开的文本预览 -->
      <div v-if="store.openFile" class="file-preview">
        <div class="preview-head">
          <span class="preview-name" :title="store.openFile.name">{{ store.openFile.name }}</span>
          <button class="ghost small" @click="closeOpenFile()">关闭</button>
        </div>
        <pre class="preview-body">{{ store.openFile.content }}</pre>
      </div>

      <template v-else>
        <div v-if="store.projectFiles && store.projectFiles.persist === false" class="v-empty">
          当前为「仅应用内」模式，未落盘文件。可在顶栏「工作目录」切换到落盘模式后，这里会自动列出你的剧本文件。
        </div>
        <template v-else-if="store.projectFiles && store.projectFiles.folders.length">
          <section v-for="g in store.projectFiles.folders" :key="g.code" class="file-sec">
            <div class="file-sec-head"><FolderIcon :open="true" /> {{ g.code }} <span class="file-sec-label">{{ g.label }}</span><span class="file-sec-count">{{ g.files.length }}</span></div>
            <div v-for="f in g.files" :key="f.name" class="file-row">
              <span class="file-ext" :class="{ extdoc: /\.(docx)$/i.test(f.name) }">{{ (f.name.split('.').pop() || '').toUpperCase() }}</span>
              <span class="file-name" :title="f.name">{{ f.name }}</span>
              <span class="file-meta">{{ fmtSize(f.size) }} · {{ fileMtime(f.mtime) }}</span>
              <span class="file-acts">
                <button v-if="isTextFile(f.name)" class="mini" @click="openProjectFile(g.code + '/' + f.name, true)">打开</button>
                <button class="mini" @click="downloadProjectFile(g.code + '/' + f.name)"><template v-if="!isTextFile(f.name)">打开</template><template v-else>下载</template></button>
              </span>
            </div>
          </section>
        </template>
        <div v-else class="v-empty">
          <template v-if="store.pid">还没有本地文件。导入原著、生成初稿或导出后，文件会自动出现在这里（数据写在 <code class="mono">data/&lt;剧名&gt;/</code>）。</template>
          <template v-else>选择剧本项目后，这里会列出该项目在磁盘上的剧本文件。</template>
        </div>
      </template>
    </div>

    <!-- 知识库 -->
    <div v-else-if="store.view === 'knowledge'" class="v-body">
      <template v-if="store.knowledge.length">
        <template v-for="g in store.knowledge" :key="g.kind">
          <div class="know-kind">{{ KIND_NAME[g.kind] || g.kind }}（{{ g.docs.length }}）</div>
          <div v-for="(d, i) in g.docs" :key="i" class="know-row">{{ d.text }}</div>
        </template>
      </template>
      <div v-else class="v-empty">还没有知识数据。导入原著会自动提取写作手法与作者风格；在对话里说「记住：…」也会记入这里。</div>
    </div>

    <!-- 版本对比 -->
    <div v-else class="v-body">
      <div v-if="store.diffMeta" class="diff-summary">{{ store.diffMeta }}</div>
      <div v-if="store.diff.length">
        <div v-for="(x, i) in store.diff" :key="i" class="diff-item">
          <span :class="diffMeta(x.t).cls">{{ diffMeta(x.t).label }}</span>
          <b class="mono">{{ x.p }}</b>
          <div>
            <template v-if="x.t === '~'">
              <span class="old">{{ fmtVal(x.before) }}</span> → <span class="new">{{ fmtVal(x.after) }}</span>
            </template>
            <template v-else>
              <span :class="diffMeta(x.t).cls">{{ fmtVal(x.before ?? x.after) }}</span>
            </template>
          </div>
        </div>
      </div>
      <div v-else class="v-empty">
        {{ store.diffMeta ? '两版之间无差异。' : '生成第二个版本后，这里会展示最新一版的改动对比。' }}
      </div>
    </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.viewer {
  background: var(--panel);
  display: flex; flex-direction: column; min-height: 0; min-width: 0;
}
.v-head { padding: 9px 12px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 6px; }
.vt { font-size: 12px; color: var(--muted); font-weight: 600; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.v-tabs { display: flex; gap: 2px; }
.v-tab {
  background: transparent; border: 1px solid transparent; color: var(--muted);
  padding: 3px 10px; border-radius: 7px; font-size: 11.5px; font-weight: 500;
}
.v-tab:hover { color: var(--ink); background: color-mix(in oklch, var(--ink) 6%, transparent); }
.v-tab.active { background: var(--select); color: var(--ink); font-weight: 600; }
.v-acts { display: flex; gap: 4px; align-items: center; position: relative; }
.export-wrap { position: relative; }
.export-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20;
  display: flex; flex-direction: column; gap: 2px; min-width: 120px;
  background: var(--panel2); border: 1px solid var(--line); border-radius: 10px; padding: 4px;
  box-shadow: 0 10px 28px oklch(0 0 0 / 0.4);
}
.export-menu button { text-align: left; }
.v-body-wrap { flex: 1; min-height: 0; display: flex; flex-direction: column; position: relative; }
.v-body { flex: 1; overflow-y: auto; min-height: 0; }
/* tab 切换：淡入淡出 + 轻微位移（out-in，避免闪烁/闪空）；全局已尊重 prefers-reduced-motion */
.tabfade-enter-active { transition: opacity var(--dur) var(--ease), transform var(--dur) var(--ease); }
.tabfade-leave-active { transition: opacity 90ms var(--ease), transform 90ms var(--ease); }
.tabfade-enter-from { opacity: 0; transform: translateY(6px); }
.tabfade-leave-to { opacity: 0; transform: translateY(-6px); }
/* 头部操作按钮群：出现 / 消失平滑淡入淡出，不再硬切 */
.vacts-enter-active, .vacts-leave-active { transition: opacity var(--dur) var(--ease); }
.vacts-enter-from, .vacts-leave-to { opacity: 0; }
/* 剧本正文：排版渲染（ScreenplayView），不再是裸 pre */
.v-body > .sp { padding: 16px 18px; }
.v-body pre {
  margin: 0; padding: 16px 18px; font-family: var(--mono);
  font-size: 14px; line-height: 1.85; white-space: pre-wrap; word-break: break-word; color: oklch(0.88 0.005 75);
}
.v-empty { color: var(--dim); font-size: 12px; padding: 16px; line-height: 1.7; }
.know-row { font-size: 11.5px; color: var(--muted); padding: 5px 12px; border-bottom: 1px dashed var(--line); }
.know-kind { font-size: 11px; color: var(--cue); padding: 10px 12px 2px; font-weight: 600; }
.diff-summary { font-size: 12px; color: var(--muted); padding: 6px 12px; }
.diff-item { font-size: 12px; padding: 6px 12px; border-bottom: 1px dashed var(--line); }
.t-add { color: var(--ok); }
.t-del { color: var(--bad); }
.t-mod { color: var(--warn); }
.v-foot {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 16px; border-top: 1px dashed var(--line); margin-top: 8px;
}
.foot-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.foot-msg { color: var(--ok); font-size: 11.5px; }
.foot-ws { background: var(--code-bg); border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; }
.notes-wrap { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-height: 100%; }
.notes-hint { font-size: 11.5px; color: var(--muted); line-height: 1.6; }
.notes-ta { flex: 1; min-height: 320px; resize: vertical; font-family: var(--mono); font-size: 12.5px; line-height: 1.7; }
.notes-foot { display: flex; align-items: center; gap: 10px; }
.notes-tip { color: var(--dim); font-size: 11px; }

/* 本地文件 */
.file-preview { display: flex; flex-direction: column; height: 100%; }
.preview-head { display: flex; align-items: center; gap: 10px; padding: 8px 16px; border-bottom: 1px solid var(--line); }
.preview-name { font-weight: 600; font-size: 12.5px; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.preview-body { flex: 1; overflow: auto; margin: 0; padding: 14px 18px; font-family: var(--mono); font-size: 13px; line-height: 1.8; white-space: pre-wrap; word-break: break-word; color: oklch(0.88 0.005 75); }
.file-sec { padding: 4px 0 4px; }
.file-sec-head { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--muted); font-weight: 600;
  padding: 8px 16px 4px; }
.file-sec-head .folder-icon { width: 14px; height: 14px; color: var(--muted); }
.file-sec-label { color: var(--dim); font-weight: 400; }
.file-sec-count { color: var(--dim); font-weight: 400; margin-left: auto; font-variant-numeric: tabular-nums; }
.file-row { display: flex; align-items: center; gap: 8px; padding: 6px 16px; font-size: 12px; min-width: 0; }
.file-row:hover { background: color-mix(in oklch, var(--ink) 4%, transparent); }
.file-ext { flex: none; font-size: 9.5px; font-family: var(--mono); color: var(--muted); border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; }
.file-ext.extdoc { color: var(--dlg); border-color: color-mix(in oklch, var(--dlg) 40%, var(--line)); }
.file-name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink); }
.file-meta { flex: none; color: var(--dim); font-size: 10.5px; font-variant-numeric: tabular-nums; }
.file-acts { display: flex; gap: 6px; flex: none; }
.file-acts .mini { background: transparent; border: 1px solid var(--line); color: var(--muted); border-radius: 6px;
  padding: 0 7px; font-size: 11px; font-weight: 500; line-height: 1.6; cursor: pointer; }
.file-acts .mini:hover { color: var(--ink); border-color: var(--line-strong); }
.mile { display: inline-flex; align-items: center; font-size: 11px; font-weight: 600; padding: 1px 9px;
  border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
.mile-final { color: var(--ok); border-color: color-mix(in oklch, var(--ok) 55%, var(--line)); }
.mile-candidate { color: var(--warn); border-color: color-mix(in oklch, var(--warn) 55%, var(--line)); }
.mile-draft { color: var(--muted); }
</style>
