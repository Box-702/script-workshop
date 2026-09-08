<script setup>
// =====================================================================
// HeaderBar.vue —— 顶栏
//
// 品牌 + 命令面板入口 + Inspector 开关。
// 桌面端使用原生窗口标题栏，不需要自定义窗口控制按钮。
// =====================================================================

import { store, toggleRightPanel, toggleLeftPanel } from '../stores/app'
import LogoMark from './LogoMark.vue'

const emit = defineEmits(['open-palette', 'open-knowledge'])
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

    <h1>
      <span class="logo" aria-hidden="true"><LogoMark :size="22" /></span>
      剧本工坊
    </h1>

    <button class="cmd-trigger" @click="emit('open-palette')">
      <span class="cmd-icon">⌘</span>
      <span class="cmd-text">搜索或执行命令…</span>
      <kbd>Ctrl+K</kbd>
    </button>

    <button class="ghost small" @click="store.showNewProject = true">＋ 新建</button>

    <!-- 记忆库 -->
    <button
      v-if="store.pid"
      class="ghost small knowledge-btn"
      title="查看 Agent 记忆库"
      @click="emit('open-knowledge')"
    >🧠 记忆</button>

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
  background: linear-gradient(180deg, color-mix(in oklch, var(--gold) 3%, var(--panel)) 0%, var(--panel) 100%);
}
h1 {
  font-size: 13px; margin: 0; display: flex; align-items: center; gap: 7px;
  font-weight: 700; letter-spacing: 0.02em; flex: none;
  background: linear-gradient(135deg, var(--ink), var(--gold));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.logo { display: inline-flex; flex: none; }
header button { flex: none; white-space: nowrap; height: 28px; padding: 0 10px; display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; }

/* 导航开关 */
.nav-toggle { padding: 0 6px; width: 28px; }
.nav-toggle svg { width: 14px; height: 14px; fill: none; stroke-width: 1.5; stroke-linecap: round; }
.nav-toggle.on { color: var(--ink); }

.cmd-trigger {
  flex: 1; max-width: 380px; height: 28px;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 0 10px; border-radius: 8px;
  background: color-mix(in oklch, var(--ink) 4%, var(--code-bg));
  border: 1px solid var(--line);
  color: var(--dim); font-size: 11.5px; cursor: pointer;
  transition: all var(--dur) var(--ease);
}
.cmd-trigger:hover { border-color: var(--line-strong); background: color-mix(in oklch, var(--ink) 6%, var(--code-bg)); }
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
</style>
