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
import WorkspaceTree from './components/WorkspaceTree.vue'
import ChatThread from './components/ChatThread.vue'
import ChatComposer from './components/ChatComposer.vue'
import ViewerPanel from './components/ViewerPanel.vue'
import CommandPalette from './components/CommandPalette.vue'
import SearchOverlay from './components/SearchOverlay.vue'
import KnowledgeModal from './components/KnowledgeModal.vue'
import NewProjectModal from './components/NewProjectModal.vue'
import WorkspaceModal from './components/WorkspaceModal.vue'
import PatchDrawer from './components/PatchDrawer.vue'
import Toast from './components/Toast.vue'
import { loadTree, loadWorkspace, loadGlobalConversations, loadWorkspaceTree, restorePanelPrefs, toggleRightPanel, toggleLeftPanel, notify, store } from './stores/app'
import { importProject } from './api'

// ---- 命令面板 ----
const paletteRef = ref(null)
const knowledgeRef = ref(null)

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
  if (!['txt', 'md', 'markdown', 'docx'].includes(ext)) {
    notify('不支持的文件格式，请上传 .txt / .md / .docx')
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
  const w = layoutEl.value.getBoundingClientRect().width - SPLITS
  const rightSpace = store.rightOpen ? MIN.right : 0
  leftW.value = clamp(leftW.value, MIN.left, w - MIN.mid - rightSpace)
  if (store.rightOpen) {
    rightW.value = clamp(rightW.value, MIN.right, w - MIN.mid - leftW.value)
  }
}

function startDrag(side, e) {
  const rect = layoutEl.value.getBoundingClientRect()
  drag = { side, avail: rect.width - SPLITS, x: e.clientX, lw: leftW.value, rw: rightW.value }
  document.body.classList.add('layout-resizing')
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', endDrag)
  e.preventDefault()
}
function onDrag(e) {
  if (!drag) return
  const dx = e.clientX - drag.x
  if (drag.side === 'left') {
    leftW.value = clamp(drag.lw + dx, MIN.left, drag.avail - MIN.mid - (store.rightOpen ? rightW.value : 0))
  } else {
    rightW.value = clamp(drag.rw - dx, MIN.right, drag.avail - MIN.mid - leftW.value)
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

watch(() => store.rightOpen, () => clampAll())

onMounted(async () => {
  restorePanelPrefs()
  clampAll()
  window.addEventListener('resize', clampAll)
  window.addEventListener('keydown', globalKey)
  await loadWorkspace()
  await loadTree()
  await loadGlobalConversations()
  await loadWorkspaceTree()
})
onUnmounted(() => {
  window.removeEventListener('resize', clampAll)
  window.removeEventListener('keydown', globalKey)
})
</script>

<template>
  <HeaderBar @open-palette="paletteRef?.openPalette()" @open-knowledge="knowledgeRef?.showModal()" />
  <!-- 拖拽导入覆盖层 -->
  <Transition name="fade">
    <div v-if="dragging" class="drop-overlay" @dragleave="onDragLeave" @drop="onDrop">
      <div class="drop-zone">
        <div class="drop-icon">📄</div>
        <div class="drop-text">松开以导入剧本文件</div>
        <div class="drop-hint">.txt / .md / .docx</div>
      </div>
    </div>
  </Transition>
  <div
    ref="layoutEl" class="layout"
    @dragenter="onDragEnter" @dragover="onDragOver"
  >
    <!-- 左：聊天 + 项目导航 + 工作区 -->
    <div class="panel-wrap" :class="{ closed: !store.leftOpen }" :style="{ '--pw': leftW + 'px' }">
      <div class="pane pane-left" :style="{ width: leftW + 'px' }">
        <div class="left-top">
          <ChatList />
        </div>
        <div class="left-divider"></div>
        <div class="left-bottom">
          <WorkspaceTree @open-workspace="store.showWorkspace = true" />
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
  </div>
  <CommandPalette ref="paletteRef" />
  <SearchOverlay />
  <KnowledgeModal ref="knowledgeRef" />
  <NewProjectModal />
  <WorkspaceModal />
  <PatchDrawer />
  <Toast />
</template>

<style scoped>
.layout {
  display: flex;
  height: calc(100vh - 44px);
  min-width: 0;
}
.pane { min-width: 0; flex: none; }
.pane-left {
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--panel, #1a1a2e); border-right: 1px solid var(--border, #222);
}
.left-top { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
.left-divider {
  flex: none; height: 1px; background: var(--border, #222);
  position: relative; cursor: row-resize;
}
.left-bottom { flex: 0 0 200px; min-height: 120px; overflow: hidden; display: flex; flex-direction: column; }
.pane-mid { display: flex; flex-direction: column; min-height: 0; min-width: 0; flex: 1; }
.split { flex: none; width: 8px; cursor: col-resize; position: relative; }
.split::before {
  content: ''; position: absolute; top: 0; bottom: 0; left: 3px; width: 2px;
  border-radius: 2px;
  background: color-mix(in oklch, var(--line) 45%, transparent);
  transition: background var(--dur) var(--ease), width var(--dur) var(--ease);
}
.split:hover::before, body.layout-resizing .split::before {
  background: var(--line-strong); width: 3px; left: 2.5px;
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
  padding: 48px 64px; border-radius: 20px;
  border: 2px dashed var(--gold); background: color-mix(in oklch, var(--gold) 5%, var(--panel));
  animation: float 3s ease-in-out infinite;
}
.drop-icon { font-size: 48px; }
.drop-text { font-size: 18px; font-weight: 600; color: var(--ink); }
.drop-hint { font-size: 13px; color: var(--muted); }
.fade-enter-active, .fade-leave-active { transition: opacity 200ms var(--ease); }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
