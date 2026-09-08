<script setup>
// =====================================================================
// AgentPanel.vue —— 子代理任务面板
//
// 展示后台运行的子代理任务列表：每个任务显示名称、状态、步骤时间线、结果摘要。
// 数据来源：store.tasks（由 SSE 事件驱动更新）。
// =====================================================================

import { computed } from 'vue'
import { store, clearCompletedTasks, refreshTasks } from '../stores/app'

const STATUS_LABEL = { pending: '排队中', running: '运行中', done: '已完成', failed: '失败' }
const STATUS_ICON = { pending: '⏳', running: '⚡', done: '✅', failed: '❌' }

const activeTasks = computed(() => store.tasks.filter((t) => t.status === 'running' || t.status === 'pending'))
const completedTasks = computed(() => store.tasks.filter((t) => t.status === 'done' || t.status === 'failed'))

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
</script>

<template>
  <div class="agent-panel">
    <!-- 活跃任务 -->
    <template v-if="activeTasks.length">
      <div class="ap-section">
        <div class="ap-sec-head"><span class="ap-pulse"></span> 运行中（{{ activeTasks.length }}）</div>
        <div v-for="task in activeTasks" :key="task.id" class="ap-card ap-active">
          <div class="ap-card-head">
            <span class="ap-icon">{{ STATUS_ICON[task.status] }}</span>
            <span class="ap-name">{{ task.name }}</span>
            <span class="ap-badge ap-running">{{ STATUS_LABEL[task.status] }}</span>
          </div>
          <div class="ap-steps">
            <div v-for="(step, i) in task.steps" :key="i" class="ap-step" :class="'ap-step-' + step.status">
              <span class="ap-step-dot"></span>
              <span class="ap-step-label">{{ step.label }}</span>
              <span v-if="step.detail" class="ap-step-detail">{{ step.detail }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 已完成任务 -->
    <template v-if="completedTasks.length">
      <div class="ap-section">
        <div class="ap-sec-head">
          已完成（{{ completedTasks.length }})
          <button class="ghost mini ap-clear" @click="clearCompletedTasks()">清除</button>
        </div>
        <div v-for="task in completedTasks" :key="task.id" class="ap-card" :class="task.status === 'failed' ? 'ap-failed' : 'ap-done'">
          <div class="ap-card-head">
            <span class="ap-icon">{{ STATUS_ICON[task.status] }}</span>
            <span class="ap-name">{{ task.name }}</span>
            <span class="ap-badge" :class="task.status === 'failed' ? 'ap-badge-fail' : 'ap-badge-done'">
              {{ STATUS_LABEL[task.status] }}
            </span>
            <span class="ap-time">{{ fmtTime(task.finished_at) }}</span>
          </div>
          <div v-if="task.result" class="ap-result">
            <pre>{{ task.result }}</pre>
          </div>
          <div v-if="task.steps.length" class="ap-steps ap-steps-compact">
            <div v-for="(step, i) in task.steps" :key="i" class="ap-step" :class="'ap-step-' + step.status">
              <span class="ap-step-dot"></span>
              <span class="ap-step-label">{{ step.label }}</span>
              <span v-if="step.detail" class="ap-step-detail">{{ step.detail }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 空态 -->
    <div v-if="!store.tasks.length" class="ap-empty">
      <div class="ap-empty-icon">🤖</div>
      <div>还没有子代理任务</div>
      <div class="ap-empty-hint">在对话中说「分析场景」「检查风格」「润色对白」等，会在这里启动专职子代理。</div>
    </div>

    <!-- 刷新按钮 -->
    <div v-if="store.tasks.length" class="ap-foot">
      <button class="ghost small" @click="refreshTasks()">刷新状态</button>
    </div>
  </div>
</template>

<style scoped>
.agent-panel { padding: 12px 14px; display: flex; flex-direction: column; gap: 12px; min-height: 100%; }
.ap-section { display: flex; flex-direction: column; gap: 8px; }
.ap-sec-head {
  font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase;
  letter-spacing: 0.04em; display: flex; align-items: center; gap: 6px;
}
.ap-pulse {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--ok); animation: pulse-dot 1.2s ease-in-out infinite;
}
@keyframes pulse-dot { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.ap-clear { margin-left: auto; }

.ap-card {
  background: var(--panel2); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 12px; display: flex; flex-direction: column; gap: 6px;
}
.ap-active { border-left: 3px solid var(--ok); }
.ap-done { border-left: 3px solid var(--cue); opacity: 0.85; }
.ap-failed { border-left: 3px solid var(--bad); }

.ap-card-head { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.ap-icon { flex: none; }
.ap-name { font-weight: 600; color: var(--ink); flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ap-badge {
  flex: none; font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted);
}
.ap-running { color: var(--ok); border-color: color-mix(in oklch, var(--ok) 50%, var(--line)); }
.ap-badge-done { color: var(--cue); border-color: color-mix(in oklch, var(--cue) 50%, var(--line)); }
.ap-badge-fail { color: var(--bad); border-color: color-mix(in oklch, var(--bad) 50%, var(--line)); }
.ap-time { flex: none; font-size: 10px; color: var(--dim); font-variant-numeric: tabular-nums; }

.ap-steps { display: flex; flex-direction: column; gap: 3px; padding-left: 4px; }
.ap-steps-compact { margin-top: 4px; }
.ap-step { display: flex; align-items: baseline; gap: 6px; font-size: 11px; color: var(--muted); }
.ap-step-dot {
  flex: none; width: 5px; height: 5px; border-radius: 50%; margin-top: 3px;
  background: var(--line);
}
.ap-step-running .ap-step-dot { background: var(--ok); animation: pulse-dot 1.2s ease-in-out infinite; }
.ap-step-done .ap-step-dot { background: var(--cue); }
.ap-step-failed .ap-step-dot { background: var(--bad); }
.ap-step-label { flex: none; }
.ap-step-detail { flex: 1; color: var(--dim); min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.ap-result {
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 10px; max-height: 240px; overflow-y: auto;
}
.ap-result pre {
  margin: 0; font-family: var(--mono); font-size: 11.5px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word; color: var(--muted);
}

.ap-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: var(--dim); text-align: center; padding: 32px 16px;
}
.ap-empty-icon { font-size: 32px; opacity: 0.5; }
.ap-empty-hint { font-size: 11px; color: var(--dim); max-width: 240px; line-height: 1.6; }

.ap-foot { margin-top: auto; padding-top: 8px; border-top: 1px dashed var(--line); display: flex; justify-content: center; }
</style>
