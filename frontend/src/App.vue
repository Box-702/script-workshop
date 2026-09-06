<script setup>
// =====================================================================
// App.vue —— 根组件：整体三栏布局（可自由左右拉伸）
//
//   ┌─────────── 顶栏 HeaderBar ───────────┐
//   │ 项目树 │ 对话区 │ 查看面板 │  （列宽可拖）
//   └─────────── 新建剧本弹窗 ─────────────┘
// 布局：左右两栏宽度可拖拽调整（localStorage 记忆），中间 Agent 聊天区自适应。
// 页面加载时先拉取状态徽章，再拉取项目树。
// =====================================================================

import { ref, onMounted, onUnmounted } from 'vue'
import HeaderBar from './components/HeaderBar.vue'
import ProjectTree from './components/ProjectTree.vue'
import ChatThread from './components/ChatThread.vue'
import ChatComposer from './components/ChatComposer.vue'
import ViewerPanel from './components/ViewerPanel.vue'
import NewProjectModal from './components/NewProjectModal.vue'
import WorkspaceModal from './components/WorkspaceModal.vue'
import PatchDrawer from './components/PatchDrawer.vue'
import Toast from './components/Toast.vue'
import { loadStatus, loadTree, loadWorkspace } from './stores/app'

// ---- 可拉伸三栏：左/右宽度可拖，中间自适应 ----
const layoutEl = ref(null)
const MIN = { left: 180, right: 260, mid: 340 }
const SPLITS = 12 // 两条 6px 分隔条占宽
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
  leftW.value = clamp(leftW.value, MIN.left, w - MIN.mid - MIN.right)
  rightW.value = clamp(rightW.value, MIN.right, w - MIN.mid - leftW.value)
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
    leftW.value = clamp(drag.lw + dx, MIN.left, drag.avail - MIN.mid - rightW.value)
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

onMounted(async () => {
  clampAll()
  window.addEventListener('resize', clampAll)
  await loadStatus()
  await loadWorkspace()
  await loadTree()
})
onUnmounted(() => window.removeEventListener('resize', clampAll))
</script>

<template>
  <HeaderBar />
  <div ref="layoutEl" class="layout">
    <!-- 左：项目树（宽可拖） -->
    <ProjectTree class="pane pane-left" :style="{ width: leftW + 'px' }" />
    <div class="split" @pointerdown="startDrag('left', $event)"></div>
    <!-- 中：对话区（消息流 + 输入框，自适应） -->
    <main class="pane-mid">
      <ChatThread />
      <ChatComposer />
    </main>
    <div class="split" @pointerdown="startDrag('right', $event)"></div>
    <!-- 右：剧本文本 / 知识库 / 版本对比（宽可拖） -->
    <ViewerPanel class="pane pane-right" :style="{ width: rightW + 'px' }" />
  </div>
  <!-- 新建剧本弹窗 + 工作目录设置 + 改编提议审阅抽屉 + 非阻塞通知 -->
  <NewProjectModal />
  <WorkspaceModal />
  <PatchDrawer />
  <Toast />
</template>

<style scoped>
.layout {
  display: flex;
  height: calc(100vh - 57px);
  min-width: 0;
}
/* 左右面板：固定为其设定宽度，不参与 flex 伸缩；min-width 0 允许收窄 */
.pane { min-width: 0; flex: none; }
.pane-mid { display: flex; flex-direction: column; min-height: 0; min-width: 0; flex: 1; }
/* 两条可拖拽分隔条：平时只留一丝痕迹（弱于普通边框），交互时才亮起来，
   减少三栏被硬线框住的感觉 */
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
</style>
