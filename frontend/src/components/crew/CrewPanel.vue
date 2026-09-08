<template>
  <div class="crew-panel">
    <div class="crew-header">
      <h4>🎬 剧组工位</h4>
      <button class="btn-ghost" @click="$emit('close')">✕</button>
    </div>

    <!-- 流水线进度 -->
    <div class="pipeline-bar">
      <div class="pipeline-label">流水线进度</div>
      <div class="pipeline-track">
        <div class="pipeline-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <div class="pipeline-text">{{ progressText }}</div>
    </div>

    <!-- Agent 卡片网格 -->
    <div class="crew-grid">
      <div
        v-for="agent in agents"
        :key="agent.name"
        :class="['agent-card', { active: agent.status === 'working' }]"
        @click="$emit('select-agent', agent.name)"
      >
        <div class="agent-icon">{{ agent.emoji }}</div>
        <div class="agent-name">{{ agent.label }}</div>
        <div :class="['agent-status', agent.status]">
          <span v-if="agent.status === 'working'" class="pulse-dot"></span>
          <span v-else class="status-text">{{ statusLabel(agent.status) }}</span>
        </div>
        <div class="agent-detail" v-if="agent.detail">{{ agent.detail }}</div>
      </div>
    </div>

    <!-- 待审批 -->
    <div v-if="pendingApprovals > 0" class="approval-alert">
      <span class="alert-icon">⏳</span>
      <span>{{ pendingApprovals }} 项待审批</span>
      <button class="btn-small ok" @click="$emit('open-approvals')">查看</button>
    </div>

    <!-- 最近任务 -->
    <div class="recent-tasks" v-if="recentTasks.length">
      <div class="section-title">最近任务</div>
      <div v-for="task in recentTasks" :key="task.id" class="task-row">
        <span :class="['task-status', task.status]">{{ taskStatusIcon(task.status) }}</span>
        <span class="task-name">{{ task.name }}</span>
        <span class="task-time">{{ formatTime(task.created_at) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  tasks: { type: Array, default: () => [] },
  stage: { type: String, default: 'idle' },
  pendingApprovals: { type: Number, default: 0 },
})

const emit = defineEmits(['close', 'select-agent', 'open-approvals'])

const stages = ['script', 'breakdown', 'style', 'prompts', 'video', 'edit', 'done']
const stageLabels = {
  idle: '待开始', script: '剧本', breakdown: '分镜', style: '风格',
  prompts: 'Prompt', video: '视频生成', edit: '剪辑', done: '完成',
}

const progressPercent = computed(() => {
  const idx = stages.indexOf(props.stage)
  if (idx < 0) return 0
  return Math.round((idx / (stages.length - 1)) * 100)
})

const progressText = computed(() => stageLabels[props.stage] || '待开始')

const recentTasks = computed(() => (props.tasks || []).slice(0, 5))

function statusLabel(s) {
  return { idle: '空闲', working: '工作中', done: '完成', error: '失败' }[s] || s
}

function taskStatusIcon(s) {
  return { running: '🟢', done: '✅', failed: '❌', pending: '⏳' }[s] || '⬜'
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.crew-panel {
  padding: 16px; background: var(--panel, #1a1a2e); border: 1px solid var(--border, #333);
  border-radius: 12px; max-width: 480px;
}
.crew-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
}
.crew-header h4 { margin: 0; font-size: 15px; }
.btn-ghost { background: none; border: none; color: var(--text2, #999); cursor: pointer; }

.pipeline-bar { margin-bottom: 16px; }
.pipeline-label { font-size: 11px; color: var(--text2, #999); margin-bottom: 4px; }
.pipeline-track {
  height: 6px; background: rgba(255,255,255,.05); border-radius: 3px; overflow: hidden;
}
.pipeline-fill {
  height: 100%; background: linear-gradient(90deg, var(--gold, #e94560), var(--violet, #a855f7));
  border-radius: 3px; transition: width .5s ease;
}
.pipeline-text { font-size: 11px; color: var(--text2, #999); margin-top: 4px; text-align: right; }

.crew-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
.agent-card {
  padding: 12px; background: rgba(255,255,255,.02); border: 1px solid var(--border, #222);
  border-radius: 8px; text-align: center; cursor: pointer; transition: all .15s;
}
.agent-card:hover { border-color: var(--gold, #e94560); }
.agent-card.active { border-color: var(--green, #4ade80); background: rgba(74,222,128,.05); }
.agent-icon { font-size: 24px; margin-bottom: 4px; }
.agent-name { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
.agent-status { font-size: 11px; }
.agent-status.idle { color: var(--text2, #666); }
.agent-status.working { color: var(--green, #4ade80); }
.agent-status.done { color: var(--cyan, #22d3ee); }
.agent-status.error { color: var(--red, #f87171); }
.agent-detail { font-size: 10px; color: var(--text2, #888); margin-top: 2px; }
.pulse-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--green, #4ade80); animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .3; } }

.approval-alert {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  background: rgba(233,69,96,.08); border: 1px solid rgba(233,69,96,.2);
  border-radius: 8px; margin-bottom: 16px; font-size: 13px;
}
.alert-icon { font-size: 16px; }
.btn-small { padding: 4px 10px; border: 1px solid var(--border, #333); border-radius: 4px; background: none; color: var(--text, #eee); cursor: pointer; font-size: 11px; }
.btn-small.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }

.section-title { font-size: 12px; color: var(--text2, #999); margin-bottom: 8px; }
.recent-tasks { }
.task-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 0;
  border-bottom: 1px solid rgba(255,255,255,.03); font-size: 12px;
}
.task-status { font-size: 12px; }
.task-name { flex: 1; }
.task-time { color: var(--text2, #666); font-size: 11px; }
</style>
