<script setup>
// =====================================================================
// ChatThread.vue —— 中间对话流
//
// 职责：
//   - 渲染品牌化开始页（空态）/ 消息列表；
//   - 智能滚动：用户停在底部时才跟随流式输出；向上滚动后出现
//     「回到最新」悬浮按钮；切换对话或发送消息时强制回底部。
// =====================================================================

import { ref, watch, nextTick } from 'vue'
import MessageItem from './MessageItem.vue'
import WelcomeHero from './WelcomeHero.vue'
import { store } from '../stores/app'

const thread = ref(null)        // 滚动容器
const nearBottom = ref(true)    // 用户是否停在底部（80px 阈值）

function onScroll() {
  const el = thread.value
  if (!el) return
  nearBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function toBottom() {
  nextTick(() => { const el = thread.value; if (el) el.scrollTop = el.scrollHeight })
}

function jumpToLatest() {
  nearBottom.value = true
  toBottom()
}

// 流式内容增长：仅当用户停在底部才跟随滚动
watch(() => store.messages.map((m) => m.content + m.events.length + m.payloads.length).join('|'),
  () => { if (nearBottom.value) toBottom() })

// 消息条数变化（切换对话 / 新发送）：视为用户主动，强制回底部
watch(() => store.messages.length, () => { nearBottom.value = true; toBottom() })
</script>

<template>
  <div class="thread-wrap">
    <div ref="thread" class="thread" @scroll.passive="onScroll">
      <div class="thread-inner">
        <!-- 空态：品牌化开始页（未选项目时引导创建，已选项目时给出改编建议） -->
        <WelcomeHero v-if="!store.messages.length" />

        <!-- 消息列表 -->
        <template v-else>
          <MessageItem v-for="(m, i) in store.messages" :key="i" :message="m" />
        </template>
      </div>
    </div>

    <!-- 向上翻阅历史时出现，点击回到最新消息 -->
    <button v-show="!nearBottom" class="jump ghost" @click="jumpToLatest">↓ 回到最新</button>
  </div>
</template>

<style scoped>
.thread-wrap { flex: 1; min-height: 0; position: relative; display: flex; }
.thread { flex: 1; overflow-y: auto; padding: 24px 28px 12px; }
.thread-inner { max-width: 820px; margin: 0 auto; }

/* 回到最新：悬浮在对话区底部中央 */
.jump {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  z-index: 5; background: var(--panel); border: 1px solid var(--line-strong);
  box-shadow: 0 6px 20px oklch(0 0 0 / 0.35);
}
</style>
