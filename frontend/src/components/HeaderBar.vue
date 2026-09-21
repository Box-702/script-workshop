<script setup>
// =====================================================================
// HeaderBar.vue —— 顶栏
//
// 品牌 + 命令面板入口 + 批次状态徽标 + Inspector 开关。
// 桌面端使用原生窗口标题栏，不需要自定义窗口控制按钮。
// =====================================================================

import { computed, onMounted } from 'vue'
import { store, toggleRightPanel, toggleLeftPanel, loadModelStatus } from '../stores/app'
import LogoMark from './LogoMark.vue'

const emit = defineEmits(['open-palette'])

// 当前生效的对话模型（顶栏徽标，点击打开设置）
const modelChip = computed(() => {
  const m = store.modelInfo
  if (!m?.available) return null
  const short = { DeepSeek: 'DS' }[m.provider] || m.provider
  return { label: `${short} · ${m.name}` }
})

function openSettings() {
  store.showSettings = true
}

onMounted(loadModelStatus)

// 批次状态徽标：批次在跑（running / awaiting_approval）时显示，点击直达视频工作台。
const batchBadge = computed(() => {
  const b = store.videoBatch
  if (!b) return null
  const pos = `${Math.min(b.current_index + 1, b.total)}/${b.total}`
  if (b.status === 'running') return { status: 'running', text: `生成中 ${pos}` }
  if (b.status === 'awaiting_approval') return { status: 'awaiting', text: `待审批 ${pos}` }
  return null
})

function openWorkbench() {
  store.view = 'video'
  if (!store.rightOpen) toggleRightPanel()
}
</script>

<template>
  <header>
    <!-- 左侧导航开关 -->
    <button
      class="ghost nav-toggle"
      :class="{ on: store.leftOpen }"
      title="切换导航（Ctrl+B）"
      @click="toggleLeftPanel"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>

    <h1 class="brand">
      <span class="logo" aria-hidden="true"><LogoMark :size="22" /></span>
      <span class="brand-name">剧本工坊</span>
      <span class="brand-mode">VIDEO AGENT</span>
    </h1>

    <button class="cmd-trigger" aria-label="搜索或执行命令" @click="emit('open-palette')">
      <span class="cmd-icon">⌕</span>
      <span class="cmd-text">搜索或执行命令…</span>
      <kbd>Ctrl+K</kbd>
    </button>

    <button
      v-if="modelChip"
      class="model-chip"
      title="当前对话模型 · 点击更换"
      @click="openSettings"
    >{{ modelChip.label }}</button>

    <button
      v-if="batchBadge"
      :class="['batch-chip', batchBadge.status]"
      title="打开视频工作台"
      @click="openWorkbench"
    >
      <span class="dot" aria-hidden="true"></span>{{ batchBadge.text }}
    </button>

    <button class="ghost small new-project" @click="store.showNewProject = true">
      <span aria-hidden="true">＋</span> 新建剧本
    </button>

    <button
      class="ghost panel-toggle"
      :class="{ on: store.rightOpen }"
      title="切换 Inspector（Ctrl+I）"
      @click="toggleRightPanel"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <rect x="2" y="2.5" width="12" height="11" rx="2" />
        <path d="M10 2.5v11" />
        <path v-if="store.rightOpen" class="fill-hint" d="M10.9 4.4h2.2v7.2h-2.2z" />
      </svg>
    </button>
  </header>
</template>

<style scoped>
header {
  display: flex; align-items: center; gap: 10px; padding: 8px 14px;
  border-bottom: 1px solid var(--line); background: var(--panel);
  min-height: 44px;
  background: var(--panel);
}
h1 {
  font-size: 13px; margin: 0; display: flex; align-items: center; gap: 7px;
  font-weight: 700; letter-spacing: 0.02em; flex: none; color: var(--ink);
}
.logo { display: inline-flex; flex: none; }
.brand-name { white-space: nowrap; }
.brand-mode {
  color: var(--gold); font: 600 9px/1 var(--mono); letter-spacing: 0.12em;
  padding: 4px 5px; border: 1px solid color-mix(in oklch, var(--gold) 35%, var(--line));
  border-radius: 5px; background: transparent;
}
header button { flex: none; white-space: nowrap; height: 28px; padding: 0 10px; display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; }

/* 导航开关 */
.nav-toggle { padding: 0 6px; width: 28px; }
.nav-toggle svg { width: 14px; height: 14px; fill: none; stroke-width: 1.5; stroke-linecap: round; }
.nav-toggle.on { color: var(--ink); }

.cmd-trigger {
  flex: 1; max-width: 380px; height: 28px;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 0 10px; border-radius: 8px;
  background: color-mix(in oklch, var(--panel2) 66%, var(--code-bg));
  border: 1px solid var(--line);
  color: var(--dim); font-size: 11.5px; cursor: pointer;
  transition: all var(--dur) var(--ease);
}
.cmd-trigger:hover { border-color: var(--line-strong); background: color-mix(in oklch, var(--ink) 4%, var(--code-bg)); }
.cmd-icon { font-size: 12px; opacity: 0.5; }
.cmd-text { flex: 1; text-align: left; }
.cmd-trigger kbd {
  font-size: 9px; font-family: var(--mono); color: var(--dim);
  background: var(--panel2); border: 1px solid var(--line);
  border-radius: 3px; padding: 0 4px; flex: none;
}

.panel-toggle { margin-left: auto; }
.panel-toggle svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.panel-toggle .fill-hint { fill: currentColor; stroke: none; opacity: 0.5; }
.panel-toggle.on { background: var(--select); border-color: var(--line-strong); color: var(--ink); }

/* 当前模型徽标：安静的文字 chip，hover 提示可点 */
.model-chip {
  height: 28px; padding: 0 10px; border-radius: 8px;
  border: 1px solid var(--line); background: transparent;
  color: var(--muted); font-size: 11px; font-family: var(--mono);
  cursor: pointer; white-space: nowrap;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.model-chip:hover { color: var(--ink); border-color: var(--line-strong, var(--line)); }

/* 批次状态徽标：生成中（青，脉冲）/ 待审批（金） */
.batch-chip {
  display: inline-flex; align-items: center; gap: 6px; height: 28px;
  padding: 0 11px; border-radius: 8px; font-size: 11.5px; font-weight: 600;
  cursor: pointer; white-space: nowrap;
  border: 1px solid color-mix(in oklch, var(--cyan) 40%, var(--line));
  color: var(--cyan);
  background: color-mix(in oklch, var(--cyan) 9%, transparent);
  transition: filter var(--dur) var(--ease);
}
.batch-chip:hover { filter: brightness(1.15); }
.batch-chip .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.batch-chip.running .dot { animation: batch-pulse 1.2s ease-in-out infinite; }
.batch-chip.awaiting {
  border-color: color-mix(in oklch, var(--gold) 45%, var(--line));
  color: var(--gold);
  background: color-mix(in oklch, var(--gold) 10%, transparent);
}
@keyframes batch-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.72); }
}

@media (max-width: 760px) {
  header { min-height: 48px; padding: 8px 10px; gap: 7px; }
  .brand-mode { display: none; }
  .cmd-trigger { max-width: none; }
  .cmd-trigger .cmd-text { display: none; }
  .cmd-trigger { flex: 0 0 38px; justify-content: center; padding: 0; }
  .cmd-trigger kbd { display: none; }
  .new-project { padding-inline: 8px; }
  .new-project { font-size: 0; }
  .new-project span { font-size: 16px; }
}
</style>
