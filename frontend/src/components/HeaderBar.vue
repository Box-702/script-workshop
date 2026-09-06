<script setup>
// =====================================================================
// HeaderBar.vue —— 顶栏
//
// 内容：品牌标记、产品名、「＋ 新建剧本」/「工作目录」按钮、
// 右侧查看面板的开合开关（面板默认收起，偏好记忆在 localStorage）。
// =====================================================================

import { computed } from 'vue'
import { store, toggleRightPanel } from '../stores/app'
import LogoMark from './LogoMark.vue'
import FolderIcon from './FolderIcon.vue'

// 工作目录是否已配置（复用 /api/workspace 信息）
const wsLabel = computed(() => {
  const w = store.workspace
  if (!w) return '工作目录'
  if (!w.persist) return '工作目录 仅应用内'
  return w.configured ? (w.mode === 'custom' ? '工作目录 ✔' : '工作目录') : '工作目录'
})
</script>

<template>
  <header>
    <h1>
      <span class="logo" aria-hidden="true"><LogoMark :size="15" /></span>
      剧本工坊 <span class="muted">对话式改编 Agent</span>
    </h1>
    <button @click="store.showWorkspace = true" :class="{ 'ws-on': store.workspace?.configured }">
      <FolderIcon class="ws-ico" :open="false" />
      {{ wsLabel }}
    </button>
    <button @click="store.showNewProject = true">＋ 新建剧本</button>
    <button
      class="ghost panel-toggle"
      :class="{ on: store.rightOpen }"
      :title="store.rightOpen ? '收起查看面板' : '打开查看面板（剧本 / 设定 / 知识库 / 对比）'"
      :aria-label="store.rightOpen ? '收起查看面板' : '打开查看面板'"
      @click="toggleRightPanel"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <rect x="2" y="2.5" width="12" height="11" rx="2" />
        <path d="M10 2.5v11" />
        <path v-if="store.rightOpen" class="fill-hint" d="M10.9 4.4h2.2v7.2h-2.2z" />
      </svg>
      查看面板
    </button>
  </header>
</template>

<style scoped>
header {
  display: flex; align-items: center; gap: 14px; padding: 11px 18px;
  border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap;
  min-height: 56px;
}
h1 { font-size: 16px; margin: 0; display: flex; align-items: center; gap: 9px; }
/* 顶栏按钮一致性：同高、单行、不收缩，带图标的按钮同间距 */
header button {
  flex: none; white-space: nowrap;
  height: 32px; padding: 0 13px;
  display: inline-flex; align-items: center; gap: 6px;
}
.logo {
  display: inline-grid; place-items: center; width: 26px; height: 26px;
  border-radius: 8px; background: var(--accent); color: var(--on-accent);
}
/* 面板开关：靠最右；开启时中性点亮 */
.panel-toggle {
  margin-left: auto;
}
.panel-toggle svg {
  width: 15px; height: 15px; fill: none;
  stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round;
}
.panel-toggle .fill-hint { fill: currentColor; stroke: none; opacity: 0.55; }
.panel-toggle.on {
  background: var(--select);
  border-color: var(--line-strong);
  color: var(--ink);
}
/* 工作目录按钮里的线稿文件夹：继承文字色，不抢徽章 */
.ws-ico { width: 13px; height: 13px; vertical-align: -2px; margin-right: 3px; }
.ws-on { border-color: color-mix(in oklch, var(--ok) 55%, var(--line)); color: var(--ok); }
.ws-on .ws-ico { color: var(--ok); }
</style>
