<script setup>
// =====================================================================
// HeaderBar.vue —— 顶栏
//
// 内容：品牌标记、产品名、「＋ 新建剧本」按钮、后端状态徽章
//（模型 / RAG / 数据库 / Checkpointer）；状态未返回前显示骨架屏。
// =====================================================================

import { computed } from 'vue'
import { store } from '../stores/app'
import LogoMark from './LogoMark.vue'
import FolderIcon from './FolderIcon.vue'

// 状态徽章文案 + 点亮样式，全部由 /api/status 派生
const badges = computed(() => {
  const s = store.status
  if (!s) return []
  if (s.error) return [{ text: `status: ${s.error}`, cls: 'off' }]
  const mode = s.mode === 'full'
    ? { text: '完整模式', cls: 'on' }
    : { text: '演示模式', cls: 'off' }
  const model = s.model.available
    ? `模型 ${s.model.provider}(${s.model.name})`
    : '模型 未配置(回退)'
  const rag = s.rag.enabled ? `RAG ${s.rag.vector_backend}·${s.rag.dim}d` : 'RAG 关闭'
  return [
    mode,
    { text: model, cls: s.model.available ? 'on' : 'off' },
    { text: rag, cls: s.rag.enabled ? 'on' : 'off' },
    { text: s.storage.database.split('://')[0], cls: '' },
    { text: s.storage.checkpointer, cls: '' },
  ]
})

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
    <div class="badges">
      <!-- 状态接口未返回：骨架屏占位 -->
      <template v-if="store.statusLoading">
        <span v-for="i in 3" :key="i" class="badge skeleton"></span>
      </template>
      <template v-else>
        <span v-for="b in badges" :key="b.text" class="badge" :class="b.cls">{{ b.text }}</span>
      </template>
    </div>
  </header>
</template>

<style scoped>
header {
  display: flex; align-items: center; gap: 14px; padding: 11px 18px;
  border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap;
  min-height: 56px;
}
h1 { font-size: 16px; margin: 0; display: flex; align-items: center; gap: 9px; }
.logo {
  display: inline-grid; place-items: center; width: 26px; height: 26px;
  border-radius: 8px; background: var(--accent); color: var(--on-accent);
}
.badges { display: flex; gap: 8px; flex-wrap: wrap; margin-left: auto; }
/* 工作目录按钮里的线稿文件夹：继承文字色，不抢徽章 */
.ws-ico { width: 13px; height: 13px; vertical-align: -2px; margin-right: 3px; }
.ws-on { border-color: color-mix(in oklch, var(--ok) 55%, var(--line)); color: var(--ok); }
.ws-on .ws-ico { color: var(--ok); }
</style>
