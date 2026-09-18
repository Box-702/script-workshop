<script setup>
// =====================================================================
// ViewerPanel.vue —— Inspector 面板（上下文感知）
//
// 两个 tab + 智能切换：
//   - 剧本编辑：标准剧本排版（可编辑/导出/复制）
//   - Agent 任务：后台子代理任务列表及进度
//   - 有活跃任务时自动切到 Agent tab，任务完成后自动切回编辑器
// =====================================================================

import { computed, ref, onUnmounted, watch } from 'vue'
import ScreenplayView from './ScreenplayView.vue'
import ScreenplayEditor from './ScreenplayEditor.vue'
import AgentPanel from './AgentPanel.vue'
import FolderTree from './FolderTree.vue'
import VideoWorkbench from './video/VideoWorkbench.vue'
import { store, showView, focusScene, exportVersion, syncProjectToWorkspace, setVersionMilestone, notify, loadViewer, saveNotes } from '../stores/app'

const TABS = [
  { key: 'editor', label: '剧本编辑', icon: '📄' },
  { key: 'scene', label: '场景聚焦', icon: '🎯' },
  { key: 'video', label: '视频工作台', icon: '🎬' },
  { key: 'agents', label: 'Agent 任务', icon: '🤖', badge: true },
]

// 聚焦场景数据
const focusedScene = computed(() => {
  if (!store.focusedSceneId || !store.viewerScript) return null
  return (store.viewerScript.scenes || []).find((s) => s.id === store.focusedSceneId) || null
})
const charMap = computed(() => {
  if (!store.viewerScript) return {}
  return (store.viewerScript.characters || []).reduce((m, c) => ((m[c.id] = c.name), m), {})
})
const currentTitle = computed(() => store.projects.find((p) => p.id === store.pid)?.title || '未选择项目')

// 活跃任务数（用于 badge）
const activeTaskCount = computed(() => store.tasks.filter((t) => t.status === 'running' || t.status === 'pending').length)

// 有新任务启动时自动切到 Agent tab
watch(activeTaskCount, (newVal, oldVal) => {
  if (newVal > oldVal && store.view !== 'agents') {
    showView('agents')
  }
})

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
// 组件卸载后不再触发状态写入。
onUnmounted(() => clearTimeout(copiedTimer))

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

/** PDF 导出：打开可打印 HTML 页面，浏览器自动弹出打印对话框。 */
function doExportPdf() {
  if (!latestVersionId.value) return
  exportOpen.value = false
  const url = `/api/versions/${latestVersionId.value}/export?fmt=pdf`
  window.open(url, '_blank')
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
        >
          <span class="v-tab-icon">{{ t.icon }}</span>
          {{ t.label }}
          <span v-if="t.badge && activeTaskCount" class="v-tab-badge">{{ activeTaskCount }}</span>
        </button>
      </div>
      <div class="vt">{{ currentTitle }}</div>
      <!-- 操作按钮：仅当有可操作的版本/文本时出现，并在出现/消失时平滑过渡，避免切换 tab 时突兀地弹出 -->
      <Transition name="vacts">
        <div v-if="store.view === 'editor' && latestVersionId" class="v-acts">
          <button v-if="store.viewerScript && !editing" class="ghost small" @click="editing = true">✎ 编辑</button>
          <div class="export-wrap">
            <button class="ghost small" @click="exportOpen = !exportOpen">
              {{ exporting ? `导出中…` : '⤓ 导出' }}
            </button>
            <div v-if="exportOpen" class="export-menu">
              <button class="ghost small" @click="doExport('txt')">.txt 纯文本</button>
              <button class="ghost small" @click="doExport('md')">.md 文档</button>
              <button class="ghost small" @click="doExport('docx')">.docx Word</button>
              <button class="ghost small" @click="doExportPdf">🖨 打印 PDF</button>
            </div>
          </div>
          <button class="ghost small" :disabled="!store.viewerText" @click="copyScript">
            {{ copied ? '✓ 已复制' : '⧉ 复制' }}
          </button>
        </div>
      </Transition>
    </div>

    <!-- 各 tab 内容：纯淡入淡出重叠 crossfade，切换时不位移、屏幕不抖动 -->
    <div class="v-body-wrap">
      <Transition name="tabfade">
    <!-- 剧本编辑：标准剧本排版 -->
    <div v-if="store.view === 'editor'" class="v-body">
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

    <!-- 场景聚焦视图 -->
    <div v-else-if="store.view === 'scene'" class="v-body">
      <div v-if="focusedScene" class="scene-focus">
        <div class="sf-header">
          <h3>{{ focusedScene.title || focusedScene.id }}</h3>
          <button class="ghost small" @click="focusScene(null); showView('editor')">✕ 退出聚焦</button>
        </div>
        <div v-if="focusedScene.purpose" class="sf-section">
          <div class="sf-label">目的</div>
          <div class="sf-text">{{ focusedScene.purpose }}</div>
        </div>
        <div v-if="focusedScene.conflict" class="sf-section">
          <div class="sf-label">冲突</div>
          <div class="sf-text">{{ focusedScene.conflict }}</div>
        </div>
        <div v-if="focusedScene.characters?.length" class="sf-section">
          <div class="sf-label">人物</div>
          <div class="sf-chars">
            <span v-for="cid in focusedScene.characters" :key="cid" class="pill dlg">{{ charMap[cid] || cid }}</span>
          </div>
        </div>
        <div v-if="focusedScene.beats?.length" class="sf-section">
          <div class="sf-label">节拍（{{ focusedScene.beats.length }}）</div>
          <div v-for="b in focusedScene.beats" :key="b.id" class="sf-beat" :class="'sf-' + b.type">
            <span class="sf-beat-id">{{ b.id }}</span>
            <span v-if="b.type === 'dialogue'" class="sf-beat-speaker">{{ charMap[b.speaker] || b.speaker }}</span>
            <span class="sf-beat-text">{{ b.line || b.text || '' }}</span>
            <span v-if="b.emotion" class="sf-beat-emotion">（{{ b.emotion }}）</span>
          </div>
        </div>
      </div>
      <div v-else class="v-empty">
        点击左侧场景列表中的某个场景，这里会显示该场景的详细内容。
      </div>
    </div>

    <!-- 视频工作台：模式切换 / 批量生成 / 审批预览 / 镜头列表 -->
    <div v-else-if="store.view === 'video'" class="v-body v-body-video">
      <VideoWorkbench />
    </div>

    <!-- Agent 任务面板 -->
    <div v-else-if="store.view === 'agents'" class="v-body v-body-agents">
      <AgentPanel />
    </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.viewer {
  background: var(--panel);
  display: flex; flex-direction: column; min-height: 0; min-width: 0;
  animation: panel-slide-in 350ms var(--ease) both;
}
@keyframes panel-slide-in {
  from { opacity: 0; transform: translateX(24px); }
  to { opacity: 1; transform: translateX(0); }
}
.v-head {
  padding: 10px 12px; border-bottom: 1px solid var(--line); display: flex; align-items: center; gap: 8px;
  animation: head-fade-in 300ms 100ms var(--ease) both;
}
@keyframes head-fade-in {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
}
.vt {
  font-size: 11px; color: var(--dim); font-weight: 500; letter-spacing: 0.01em;
  flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  padding-left: 12px; border-left: 1px solid var(--line);
  display: flex; align-items: center;
}
.v-tabs { display: flex; gap: 2px; flex: none; overflow-x: auto; scrollbar-width: none; }
.v-tab {
  background: transparent; border: 1px solid transparent; color: var(--muted);
  padding: 4px 8px; border-radius: 7px; font-size: 11.5px; font-weight: 500;
  white-space: nowrap; flex: none;
  transition: all 200ms var(--ease);
  animation: tab-pop 250ms var(--ease-bounce) both;
}
.v-tab:nth-child(1) { animation-delay: 120ms; }
.v-tab:nth-child(2) { animation-delay: 180ms; }
@keyframes tab-pop {
  from { opacity: 0; transform: translateY(-4px) scale(0.9); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.v-tab:hover { color: var(--ink); background: color-mix(in oklch, var(--ink) 6%, transparent); }
.v-tab.active { background: var(--select); color: var(--ink); font-weight: 600; }
.v-tab-icon { font-size: 12px; }
.v-tab-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; border-radius: 999px;
  background: var(--ok); color: var(--on-accent); font-size: 9px; font-weight: 700;
  padding: 0 4px; margin-left: 4px;
}
.v-acts { display: flex; gap: 4px; align-items: center; position: relative; }
.export-wrap { position: relative; }
.export-menu {
  position: absolute; right: 0; top: calc(100% + 4px); z-index: 20;
  display: flex; flex-direction: column; gap: 2px; min-width: 120px;
  background: var(--panel2); border: 1px solid var(--line); border-radius: 10px; padding: 4px;
  box-shadow: 0 10px 28px oklch(0 0 0 / 0.4);
  animation: menu-pop 200ms var(--ease-bounce) both;
  transform-origin: top right;
}
@keyframes menu-pop {
  from { opacity: 0; transform: scale(0.9) translateY(-4px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.export-menu button { text-align: left; }
.v-body-wrap { flex: 1; min-height: 0; position: relative; overflow: hidden; }
.v-body { position: absolute; inset: 0; overflow-y: auto; min-height: 0; scrollbar-gutter: stable; }
/* tab 切换：淡入 + 微上移 */
.tabfade-enter-active { transition: opacity 250ms var(--ease), transform 250ms var(--ease); }
.tabfade-leave-active { transition: opacity 150ms ease-in, transform 150ms ease-in; }
.tabfade-enter-from { opacity: 0; transform: translateY(6px); }
.tabfade-leave-to { opacity: 0; transform: translateY(-4px); }
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
.v-body-agents { padding: 0; }
.v-foot {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 16px; border-top: 1px dashed var(--line); margin-top: 8px;
}
.foot-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.foot-msg { color: var(--ok); font-size: 11.5px; }
.foot-ws { background: var(--code-bg); border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; }
.mile { display: inline-flex; align-items: center; font-size: 11px; font-weight: 600; padding: 1px 9px;
  border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
.mile-final { color: var(--ok); border-color: color-mix(in oklch, var(--ok) 55%, var(--line)); }
.mile-candidate { color: var(--warn); border-color: color-mix(in oklch, var(--warn) 55%, var(--line)); }
.mile-draft { color: var(--muted); }

/* 场景聚焦视图 */
.scene-focus { padding: 16px; }
.sf-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.sf-header h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--ink); }
.sf-section { margin-bottom: 14px; }
.sf-label { font-size: 10px; font-weight: 600; color: var(--dim); text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 4px; }
.sf-text { font-size: 13px; color: var(--ink); line-height: 1.6; }
.sf-chars { display: flex; gap: 4px; flex-wrap: wrap; }
.sf-beat {
  display: flex; align-items: baseline; gap: 8px; padding: 4px 0;
  border-bottom: 1px dashed color-mix(in oklch, var(--ink) 6%, transparent);
  font-size: 12.5px;
}
.sf-beat-id { font-size: 10px; color: var(--dim); font-family: var(--mono); flex: none; width: 48px; }
.sf-beat-speaker { font-weight: 600; color: var(--ok); flex: none; }
.sf-beat-text { flex: 1; color: var(--ink); }
.sf-beat-emotion { font-size: 11px; color: var(--dim); font-style: italic; flex: none; }
.sf-dialogue .sf-beat-text { color: var(--ink); }
.sf-cue .sf-beat-text { color: var(--dim); font-style: italic; }
</style>
