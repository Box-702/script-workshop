<script setup>
// =====================================================================
// App.vue —— 根组件：创作工作台布局
//
//   ┌─────────── 顶栏（品牌 + 命令面板入口 + Inspector 开关）────────┐
//   │ 项目/场景导航 │ 创作区（对话 + 编辑） │ Inspector 面板 │
//   └────────────── 命令面板 (Ctrl+K) ──────────────────────────┘
// =====================================================================

import { ref, onMounted, onUnmounted, watch } from 'vue'
import HeaderBar from './components/HeaderBar.vue'
import ProjectTree from './components/ProjectTree.vue'
import ChatList from './components/ChatList.vue'
import AssetPanel from './components/AssetPanel.vue'
import ChatThread from './components/ChatThread.vue'
import ChatComposer from './components/ChatComposer.vue'
import ViewerPanel from './components/ViewerPanel.vue'
import CommandPalette from './components/CommandPalette.vue'
import SearchOverlay from './components/SearchOverlay.vue'
import NewProjectModal from './components/NewProjectModal.vue'
import WorkspaceModal from './components/WorkspaceModal.vue'
import SettingsModal from './components/settings/SettingsModal.vue'
import PatchDrawer from './components/PatchDrawer.vue'
import Toast from './components/Toast.vue'
import { loadTree, loadWorkspace, loadGlobalConversations, loadWorkspaceTree, restorePanelPrefs, toggleRightPanel, toggleLeftPanel, notify, store, pollVideoBatch, ensureBatchPolling, loadModelStatus } from './stores/app'
import { importProject } from './api'

// ---- 命令面板 ----
const paletteRef = ref(null)

// ---- 拖拽导入 ----
const dragging = ref(false)
let dragCounter = 0
function onDragEnter(e) {
  e.preventDefault()
  dragCounter++
  if (e.dataTransfer?.types?.includes('Files')) dragging.value = true
}
function onDragLeave(e) {
  e.preventDefault()
  dragCounter--
  if (dragCounter <= 0) { dragging.value = false; dragCounter = 0 }
}
function onDragOver(e) { e.preventDefault() }
async function onDrop(e) {
  e.preventDefault()
  dragging.value = false
  dragCounter = 0
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['txt', 'md', 'markdown', 'docx', 'pdf'].includes(ext)) {
    notify('不支持的文件格式，请上传 .txt / .md / .docx / .pdf')
    return
  }
  try {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('title', file.name.replace(/\.[^.]+$/, ''))
    fd.append('adaptation_type', 'short_drama')
    const r = await importProject(fd)
    await loadTree()
    notify(`已导入《${r.title}》`, 'ok')
  } catch (err) {
    notify('导入失败：' + err.message)
  }
}

// ---- 可拉伸三栏 ----
const layoutEl = ref(null)
const MIN = { left: 200, right: 280, mid: 360 }
const SPLITS = 8
const readW = (key, def) => {
  const n = Number(localStorage.getItem('sw-layout:' + key))
  return Number.isFinite(n) && n >= 60 ? n : def
}
const leftW = ref(readW('left', 260))
const rightW = ref(readW('right', 360))

let drag = null
const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi)
function clampAll() {
  if (!layoutEl.value) return
  const w = Math.max(0, layoutEl.value.getBoundingClientRect().width - SPLITS)
  const rightSpace = store.rightOpen ? MIN.right : 0
  const leftMax = Math.max(MIN.left, w - MIN.mid - rightSpace)
  leftW.value = clamp(leftW.value, MIN.left, leftMax)
  if (store.rightOpen) {
    const rightMax = Math.max(MIN.right, w - MIN.mid - leftW.value)
    rightW.value = clamp(rightW.value, MIN.right, rightMax)
  }
}

function startDrag(side, e) {
  if (!layoutEl.value || window.innerWidth < 760) return
  const rect = layoutEl.value.getBoundingClientRect()
  drag = { side, avail: rect.width - SPLITS, x: e.clientX, lw: leftW.value, rw: rightW.value }
  document.body.classList.add('layout-resizing')
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', endDrag)
  e.preventDefault()
}
function onDrag(e) {
  if (!drag) return
  if (e.buttons === 0) { endDrag(); return }
  const dx = e.clientX - drag.x
  if (drag.side === 'left') {
    leftW.value = clamp(
      drag.lw + dx,
      MIN.left,
      Math.max(MIN.left, drag.avail - MIN.mid - (store.rightOpen ? rightW.value : 0)),
    )
  } else {
    rightW.value = clamp(
      drag.rw - dx,
      MIN.right,
      Math.max(MIN.right, drag.avail - MIN.mid - leftW.value),
    )
  }
}
function endDrag() {
  if (!drag) return
  localStorage.setItem('sw-layout:left', String(Math.round(leftW.value)))
  localStorage.setItem('sw-layout:right', String(Math.round(rightW.value)))
  drag = null
  document.body.classList.remove('layout-resizing')
  window.removeEventListener('pointermove', onDrag)
  window.removeEventListener('pointerup', endDrag)
}

// Ctrl+B 切换左侧导航，Ctrl+I 切换右侧 Inspector
function globalKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
    e.preventDefault()
    toggleLeftPanel()
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
    e.preventDefault()
    toggleRightPanel()
  }
}

// ---- 响应式：≤1023px 面板抽屉化 ----
// 桌面（≥1024px）：左/中/右三栏 + 拖拽分隔条（原行为）。
// 平板/移动（≤1023px）：左右面板变成覆盖式抽屉（fixed + 遮罩），
// 选中项目 / 对话后自动收起，任何视口不出现横向溢出。
const isNarrow = ref(window.innerWidth < 1024)
function onResize() {
  isNarrow.value = window.innerWidth < 1024
  clampAll()
}
// 窄屏下选中项目 / 对话 → 收起抽屉（内容已切到中间列，面板挡视线）
watch(() => [store.pid, store.convId], () => {
  if (!isNarrow.value) return
  store.leftOpen = false
  store.rightOpen = false
})
// 窄屏下右栏视图切换（如场景聚焦）同理收起左栏
watch(() => store.view, () => {
  if (isNarrow.value && store.rightOpen) store.leftOpen = false
})

// ---- 左栏分段：对话 / 项目 / 素材 ----
// 工作区（本地文件夹映射）对单机用途没意义，换成素材面板：上传/登记参考视频。
const LEFT_TABS = ['chat', 'project', 'assets']
const _savedTab = localStorage.getItem('sw-left-tab')
const leftTab = ref(LEFT_TABS.includes(_savedTab) ? _savedTab : 'chat')
function switchLeftTab(tab) {
  leftTab.value = tab
  localStorage.setItem('sw-left-tab', tab)
}

watch(() => store.rightOpen, () => clampAll())

onMounted(async () => {
  restorePanelPrefs()
  // 窄屏首屏：抽屉默认收起（覆盖 restorePanelPrefs 的桌面默认值）
  if (isNarrow.value) {
    store.leftOpen = false
    store.rightOpen = false
  }
  clampAll()
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', globalKey)
  await loadWorkspace()
  await loadTree()
  await loadGlobalConversations()
  await loadWorkspaceTree()
  // 启动时若已有进行中的批次，立刻接上全局轮询（刷新页面不断进度）
  await pollVideoBatch()
  ensureBatchPolling()
  await loadModelStatus()
})
onUnmounted(() => {
  endDrag()
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', globalKey)
})
</script>

<template>
  <HeaderBar @open-palette="paletteRef?.openPalette()" />
  <!-- 拖拽导入覆盖层 -->
  <Transition name="fade">
    <div v-if="dragging" class="drop-overlay" @dragleave="onDragLeave" @drop="onDrop">
      <div class="drop-zone">
        <div class="drop-icon">DROP</div>
        <div class="drop-text">松开以导入剧本文件</div>
        <div class="drop-hint">.txt / .md / .docx / .pdf</div>
      </div>
    </div>
  </Transition>
  <div
    ref="layoutEl" class="layout"
    @dragenter="onDragEnter" @dragover="onDragOver"
  >
    <!-- 左：对话 / 项目 / 素材（桌面=分栏；窄屏=抽屉） -->
    <div class="panel-wrap panel-left-wrap" :class="{ closed: !store.leftOpen }" :style="{ '--pw': leftW + 'px' }">
      <div class="pane pane-left" :style="{ width: leftW + 'px' }">
        <div class="left-tabs seg-tabs" role="tablist">
          <button
            :class="['ltab', 'seg-tab', { active: leftTab === 'chat' }]"
            role="tab" :aria-selected="leftTab === 'chat'"
            @click="switchLeftTab('chat')"
          >对话</button>
          <button
            :class="['ltab', 'seg-tab', { active: leftTab === 'project' }]"
            role="tab" :aria-selected="leftTab === 'project'"
            @click="switchLeftTab('project')"
          >项目</button>
          <button
            :class="['ltab', 'seg-tab', { active: leftTab === 'assets' }]"
            role="tab" :aria-selected="leftTab === 'assets'"
            @click="switchLeftTab('assets')"
          >素材</button>
        </div>
        <div class="left-body">
          <ChatList v-if="leftTab === 'chat'" />
          <ProjectTree v-else-if="leftTab === 'project'" />
          <AssetPanel v-else />
        </div>
      </div>
      <div class="split" @pointerdown="startDrag('left', $event)"></div>
    </div>
    <!-- 中：创作区 -->
    <main class="pane-mid">
      <ChatThread />
      <ChatComposer />
    </main>
    <!-- 右：Inspector 面板 -->
    <div class="panel-wrap panel-right-wrap" :class="{ closed: !store.rightOpen }" :style="{ '--pw': rightW + 'px' }">
      <div class="split" @pointerdown="startDrag('right', $event)"></div>
      <ViewerPanel class="pane pane-right" :style="{ width: rightW + 'px' }" />
    </div>
    <!-- 窄屏抽屉遮罩：任一面板打开时出现，点击关闭 -->
    <Transition name="fade">
      <div
        v-if="isNarrow && (store.leftOpen || store.rightOpen)"
        class="drawer-scrim"
        aria-hidden="true"
        @click="store.leftOpen = false; store.rightOpen = false"
      ></div>
    </Transition>
  </div>
  <CommandPalette ref="paletteRef" />
  <SearchOverlay />
  <NewProjectModal />
  <WorkspaceModal />
  <SettingsModal
    :open="store.showSettings"
    @close="store.showSettings = false; loadModelStatus()"
  />
  <PatchDrawer />
  <Toast />
</template>

<style scoped>
.layout {
  display: flex;
  height: calc(100dvh - var(--header-h));
  min-width: 0;
  position: relative;
}
.pane { min-width: 0; flex: none; }
.pane-left {
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--panel);
  border-right: 1px solid var(--line);
}
/* 左栏分段头：对话 / 项目 / 素材 —— 极简分段造型见 style.css 的 .seg-tabs/.seg-tab */
.left-tabs {
  flex: none; margin: 8px 8px 9px;
}
.ltab { flex: 1; }
.left-body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.left-body > * { flex: 1; min-height: 0; }
.pane-mid { display: flex; flex-direction: column; min-height: 0; min-width: 0; flex: 1; }
.split { flex: none; width: 8px; cursor: col-resize; position: relative; }
.split::before {
  content: ''; position: absolute; top: 0; bottom: 0; left: 3px; width: 2px;
  border-radius: 2px;
  background: color-mix(in oklch, var(--line) 45%, transparent);
  transition: background var(--dur) var(--ease), width var(--dur) var(--ease);
}
.split:hover::before, body.layout-resizing .split::before {
  background: var(--gold); width: 2px; left: 3px;
}

/* 面板容器：始终渲染，用 width + opacity 过渡实现开合 */
.panel-wrap {
  display: flex; flex: none;
  width: calc(var(--pw) + 8px); /* 面板宽度 + 分隔条 */
  opacity: 1;
  overflow: hidden;
  transition: width 320ms var(--ease), opacity 250ms var(--ease);
}
.panel-wrap.closed {
  width: 0;
  opacity: 0;
}
/* 右侧面板：从右侧展开 */
.panel-right-wrap {
  transition: width 320ms var(--ease), opacity 250ms var(--ease);
}

/* 拖拽导入覆盖层 */
.drop-overlay {
  position: fixed; inset: 0; z-index: 9000;
  background: color-mix(in oklch, var(--bg) 85%, transparent);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
}
.drop-zone {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  padding: 46px 64px; border-radius: 18px;
  border: 1px dashed var(--gold);
  background: var(--panel);
  box-shadow: 0 20px 52px oklch(0.03 0.02 278 / 0.34);
}
.drop-icon {
  display: grid; place-items: center; width: 72px; height: 72px; border-radius: 22px;
  border: 1px solid color-mix(in oklch, var(--gold) 55%, var(--line));
  color: var(--gold); font: 700 12px/1 var(--mono); letter-spacing: 0.12em;
  background: color-mix(in oklch, var(--gold) 8%, transparent);
}
.drop-text { font-size: 18px; font-weight: 600; color: var(--ink); }
.drop-hint { font-size: 13px; color: var(--muted); }
.fade-enter-active, .fade-leave-active { transition: opacity 200ms var(--ease); }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ---------- 响应式：≤1023px 面板抽屉化 ---------- */
/* 左右面板统一为覆盖式抽屉（fixed + 遮罩），中间列保持全宽；
   开合由 store.leftOpen / rightOpen 驱动，选中内容后自动收起。 */
@media (max-width: 1023px) {
  .layout { height: calc(100dvh - var(--header-h)); }
  .split { display: none; }
  .panel-wrap,
  .panel-wrap.panel-right-wrap {
    position: fixed;
    top: var(--header-h); bottom: 0;
    z-index: 60;
    width: min(86vw, 400px) !important;
    background: var(--panel);
    box-shadow: var(--shadow-3);
    transition: transform 280ms var(--ease), visibility 280ms;
  }
  .panel-wrap.panel-left-wrap { left: 0; border-right: 1px solid var(--line); }
  .panel-wrap.panel-right-wrap { right: 0; border-left: 1px solid var(--line); }
  .panel-wrap .pane { width: 100% !important; height: 100%; }
  /* 抵消桌面的 width+opacity 塌缩：抽屉用 transform 出入场 */
  .panel-wrap.closed {
    width: min(86vw, 400px) !important;
    opacity: 1;
    visibility: hidden;
    pointer-events: none;
  }
  .panel-wrap.panel-left-wrap.closed { transform: translateX(-102%); }
  .panel-wrap.panel-right-wrap.closed { transform: translateX(102%); }
  .pane-mid { width: 100%; }
  .drawer-scrim {
    position: fixed;
    top: var(--header-h); left: 0; right: 0; bottom: 0;
    z-index: 55;
    background: oklch(0 0 0 / .45);
  }
}

@media (max-width: 760px) {
  .drop-zone { width: min(86vw, 360px); padding: 36px 22px; text-align: center; }
  .drop-text { font-size: 16px; }
}
</style>