<script setup>
// =====================================================================
// MessageItem.vue —— 单条消息
//
// 布局（Codex 式但修正了用户气泡宽度的 bug）：
//   - 用户消息：紧凑的灰色气泡，右对齐，最大约 82% 宽。
//     （修复：不再用「inline-block 外层 + 内部百分比 max-width」的嵌套，
//       那会造成 shrink-to-fit 循环依赖，把气泡挤压成一字符一行的竖直窄条。
//       改为让气泡直接作为 .msg(flex, 宽度确定) 的 flex item，百分比能正确解析。）
//   - 助手回复：通栏直出（不套气泡），内容占满对话列宽度；
//   - 助手消息 hover 可复制原文。
// 结构：活动 chips（工具调用）→ 正文 → 载荷卡片（摘要条 / 版本卡）。
// =====================================================================

import { computed, ref, onUnmounted } from 'vue'
import PatchSummaryCard from './PatchSummaryCard.vue'
import VersionCard from './VersionCard.vue'
import { mdToHtml, esc } from '../utils/markdown'

const props = defineProps({
  message: { type: Object, required: true }, // { role, content, events, payloads, streaming }
})

const isUser = computed(() => props.message.role === 'user')
// 正文 HTML：assistant 走 Markdown，user 纯文本转义 + 换行
const bodyHtml = computed(() =>
  isUser.value ? esc(props.message.content || '') : mdToHtml(props.message.content || ''))

// 是否显示复制按钮：仅 assistant 完整回复，且没有载荷卡片（避免遮挡）
const showCopy = computed(() =>
  !isUser.value && props.message.content && !props.message.streaming && !props.message.payloads.length)

// ---- 复制原文 ----
const copied = ref(false)
let copiedTimer = null
async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content || '')
    copied.value = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => (copied.value = false), 1400)
  } catch { /* 剪贴板不可用时静默 */ }
}
// 组件卸载后不再触发状态写入。
onUnmounted(() => clearTimeout(copiedTimer))
</script>

<template>
  <div class="msg" :class="isUser ? 'user' : 'assistant'">
    <!-- 工具调用活动 chips -->
    <div v-if="!isUser && message.events.length" class="activity">
      <template v-for="(e, i) in message.events" :key="i">
        <div v-if="e.type === 'tool_call'" class="chip"><span class="fn">🔧 {{ e.name }}</span> {{ e.args || '' }}</div>
        <div v-else class="chip ok">✔ {{ e.name }}：{{ e.summary || '' }}</div>
      </template>
    </div>

    <!-- 用户：直接作为 .msg(flex, 宽度确定) 的 flex item，百分比 max-width 能正确解析 -->
    <template v-if="isUser">
      <div v-if="message.content" class="bubble" v-html="bodyHtml"></div>
      <div v-else class="typing"><i></i><i></i><i></i></div>
    </template>

    <!-- 助手：通栏直出 + 复制按钮 -->
    <template v-else>
      <div v-if="message.content || !message.streaming" class="content-wrap" :class="{ 'has-copy': showCopy }">
        <div class="content md" v-html="bodyHtml"></div>
        <button v-if="showCopy" class="copy" :aria-label="copied ? '已复制' : '复制原文'" @click="copyContent">
          {{ copied ? '✓ 已复制' : '⧉ 复制' }}
        </button>
      </div>
      <div v-else class="typing"><i></i><i></i><i></i></div>
    </template>

    <!-- 载荷卡片 -->
    <template v-for="(p, i) in message.payloads" :key="i">
      <PatchSummaryCard v-if="p.type === 'patch_review'" :payload="p" />
      <VersionCard v-else-if="p.type === 'version_applied'" :payload="p" />
    </template>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  margin-bottom: 18px;
}
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }

/* 用户气泡：直接 flex item，宽度由内容决定、受 max-width 约束 */
.bubble {
  max-width: min(82%, 560px);
  padding: 8px 14px;
  border-radius: 16px;
  border-bottom-right-radius: 6px;
  background: var(--user);
  border: 1px solid var(--user-line);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  text-align: left;
  line-height: 1.5;
  color: var(--ink);
}

/* 工具调用活动 chips：占满一整行 */
.activity { display: flex; flex-direction: column; gap: 3px; margin-bottom: 6px; flex: 1 1 100%; }

/* 助手正文：通栏 */
.content-wrap { display: flex; flex-direction: column; min-width: 0; max-width: 100%; flex: 1 1 100%; }
.content { display: block; min-width: 0; word-break: break-word; text-align: left; }

/* 复制按钮 */
.copy {
  display: block; margin-top: 2px;
  background: transparent; border: 1px solid transparent; color: var(--muted);
  font-size: 11px; font-weight: 500; padding: 2px 8px; border-radius: 4px;
  opacity: 0; pointer-events: none; width: fit-content;
}
.content-wrap:hover .copy { opacity: 1; pointer-events: auto; }
.copy:hover { color: var(--ink); background: var(--panel2); border-color: var(--line); }
</style>
