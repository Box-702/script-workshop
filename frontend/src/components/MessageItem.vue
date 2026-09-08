<script setup>
// =====================================================================
// MessageItem.vue —— 消息渲染（创新设计）
//
// 设计理念：从「聊天气泡」转型为「创作工作台的行内注释」。
// - 用户消息：简洁的指令条，像编辑器的命令输入
// - Agent 回复：通栏注释，带可折叠的工作步骤面板
// - 工具调用：折叠的「工作步骤」面板，每个步骤有图标+状态
// - 载荷卡片：审阅建议 / 版本通知
// =====================================================================

import { computed, ref, onUnmounted } from 'vue'
import PatchSummaryCard from './PatchSummaryCard.vue'
import VersionCard from './VersionCard.vue'
import { mdToHtml, esc } from '../utils/markdown'

const props = defineProps({
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
const bodyHtml = computed(() =>
  isUser.value ? esc(props.message.content || '') : mdToHtml(props.message.content || ''))

const showCopy = computed(() =>
  !isUser.value && props.message.content && !props.message.streaming && !props.message.payloads?.length)

// ---- 工作步骤面板（替代 chips）----
const SUBAGENT_TOOLS = new Set(['analyze_scenes', 'check_style', 'polish_dialogue'])
const stepsExpanded = ref(false)
const STEP_COLLAPSE = 3
const visibleEvents = computed(() => {
  const evts = props.message.events || []
  if (evts.length <= STEP_COLLAPSE || stepsExpanded.value) return evts
  return evts.slice(-STEP_COLLAPSE)
})
const hiddenCount = computed(() => Math.max(0, (props.message.events || []).length - STEP_COLLAPSE))

function stepIcon(e) {
  if (e.type === 'tool_call' && SUBAGENT_TOOLS.has(e.name)) return '🤖'
  if (e.type === 'tool_call') return '⚙️'
  if (e.type === 'step') return '⏳'
  return '✅'
}
function stepLabel(e) {
  if (e.type === 'tool_call') return e.name
  if (e.type === 'step') return e.label || e.name
  return e.name
}
function stepDetail(e) {
  if (e.type === 'tool_call') return e.args || ''
  if (e.type === 'step') return ''
  return e.summary || ''
}

// ---- 复制 ----
const copied = ref(false)
let copiedTimer = null
async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content || '')
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copied.value = false), 1400)
  } catch {}
}
onUnmounted(() => clearTimeout(copiedTimer))
</script>

<template>
  <div class="msg" :class="isUser ? 'user' : 'agent'">
    <!-- 用户：简洁指令条 -->
    <template v-if="isUser">
      <div v-if="message.content" class="cmd-bar">
        <span class="cmd-prompt">›</span>
        <span class="cmd-text" v-html="bodyHtml"></span>
      </div>
    </template>

    <!-- Agent：行内注释风格 -->
    <template v-else>
      <!-- 工作步骤面板 -->
      <div v-if="(message.events || []).length" class="steps-panel">
        <div class="steps-header" @click="stepsExpanded = !stepsExpanded">
          <span class="steps-icon">{{ message.streaming ? '⚡' : '📋' }}</span>
          <span class="steps-title">
            {{ message.streaming ? '正在工作…' : `${(message.events || []).length} 个步骤` }}
          </span>
          <span class="steps-toggle">{{ stepsExpanded ? '收起' : '展开' }}</span>
        </div>
        <div v-if="stepsExpanded || (message.events || []).length <= STEP_COLLAPSE" class="steps-body">
          <div v-if="hiddenCount > 0 && !stepsExpanded" class="steps-more" @click="stepsExpanded = true">
            还有 {{ hiddenCount }} 个步骤…
          </div>
          <div v-for="(e, i) in visibleEvents" :key="i" class="step-row" :class="'step-' + (e.type === 'tool_call' ? 'call' : e.type === 'step' ? 'progress' : 'done')">
            <span class="step-icon">{{ stepIcon(e) }}</span>
            <span class="step-label">{{ stepLabel(e) }}</span>
            <span v-if="stepDetail(e)" class="step-detail">{{ stepDetail(e) }}</span>
          </div>
        </div>
      </div>

      <!-- 正文 -->
      <div v-if="message.content || !message.streaming" class="agent-body" :class="{ 'has-copy': showCopy }">
        <div class="content md" v-html="bodyHtml"></div>
        <button v-if="showCopy" class="copy" @click="copyContent">{{ copied ? '✓ 已复制' : '⧉ 复制' }}</button>
      </div>
      <div v-else class="typing"><i></i><i></i><i></i></div>

      <!-- 载荷卡片 -->
      <template v-for="(p, i) in message.payloads" :key="i">
        <PatchSummaryCard v-if="p.type === 'patch_review'" :payload="p" />
        <VersionCard v-else-if="p.type === 'version_applied'" :payload="p" />
      </template>
    </template>
  </div>
</template>

<style scoped>
.msg { display: flex; flex-direction: column; width: 100%; margin-bottom: 16px; }
.msg.user { align-items: flex-end; }
.msg.agent { align-items: stretch; }

/* 用户指令条 */
.cmd-bar {
  display: inline-flex; align-items: baseline; gap: 8px;
  max-width: min(80%, 560px); padding: 7px 14px;
  background: var(--user); border: 1px solid var(--user-line);
  border-radius: 10px; border-bottom-right-radius: 4px;
}
.cmd-prompt { color: var(--gold); font-weight: 700; font-size: 14px; flex: none; }
.cmd-text { font-size: 13.5px; color: var(--ink); line-height: 1.5; white-space: pre-wrap; word-break: break-word; }

/* 工作步骤面板 */
.steps-panel {
  background: var(--panel2); border: 1px solid var(--line); border-radius: 10px;
  margin-bottom: 8px; overflow: hidden;
}
.steps-header {
  display: flex; align-items: center; gap: 8px; padding: 7px 12px;
  cursor: pointer; user-select: none; font-size: 12px;
}
.steps-header:hover { background: color-mix(in oklch, var(--ink) 3%, transparent); }
.steps-icon { flex: none; }
.steps-title { flex: 1; color: var(--muted); font-weight: 500; }
.steps-toggle { flex: none; color: var(--dim); font-size: 11px; }
.steps-body { padding: 4px 12px 8px; display: flex; flex-direction: column; gap: 3px; }
.steps-more {
  font-size: 11px; color: var(--dim); padding: 3px 0; cursor: pointer;
}
.steps-more:hover { color: var(--muted); }
.step-row { display: flex; align-items: baseline; gap: 6px; font-size: 11.5px; color: var(--muted); padding: 2px 0; }
.step-icon { flex: none; width: 16px; text-align: center; }
.step-label { flex: none; font-weight: 500; }
.step-detail { flex: 1; color: var(--dim); min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.step-call .step-label { color: var(--ink); }
.step-progress .step-label { color: var(--warn); }
.step-done .step-label { color: var(--ok); }

/* Agent 正文 */
.agent-body { display: flex; flex-direction: column; min-width: 0; max-width: 100%; position: relative; }
.content { display: block; min-width: 0; word-break: break-word; text-align: left; }
.copy {
  display: block; margin-top: 2px; background: transparent; border: 1px solid transparent;
  color: var(--muted); font-size: 11px; padding: 2px 8px; border-radius: 4px;
  opacity: 0; pointer-events: none; width: fit-content;
}
.agent-body:hover .copy { opacity: 1; pointer-events: auto; }
.copy:hover { color: var(--ink); background: var(--panel2); border-color: var(--line); }
</style>
