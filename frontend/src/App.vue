<script setup>
// =====================================================================
// App.vue —— 根组件：整体三栏布局
//
//   ┌─────────── 顶栏 HeaderBar ───────────┐
//   │ 项目树   │   对话区    │  查看面板    │
//   └─────────── 新建剧本弹窗 ─────────────┘
// 页面加载时先拉取状态徽章，再拉取项目树。
// =====================================================================

import { onMounted } from 'vue'
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

onMounted(async () => {
  await loadStatus()
  await loadWorkspace()
  await loadTree()
})
</script>

<template>
  <HeaderBar />
  <div class="layout">
    <!-- 左：项目树 -->
    <ProjectTree />
    <!-- 中：对话区（消息流 + 输入框） -->
    <main>
      <ChatThread />
      <ChatComposer />
    </main>
    <!-- 右：剧本文本 / 知识库 / 版本对比 -->
    <ViewerPanel />
  </div>
  <!-- 新建剧本弹窗 + 工作目录设置 + 改编提议审阅抽屉 + 非阻塞通知 -->
  <NewProjectModal />
  <WorkspaceModal />
  <PatchDrawer />
  <Toast />
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 260px 1fr 320px;
  height: calc(100vh - 52px);
}
main { display: flex; flex-direction: column; min-height: 0; min-width: 0; }
</style>
