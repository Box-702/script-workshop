<script setup>
// =====================================================================
// ChatThread.vue —— 中间对话流
//
// 职责：
//   - 渲染引导空态 / 欢迎语 + 建议操作 / 消息列表；
//   - 智能滚动：用户停在底部时才跟随流式输出；向上滚动后出现
//     「回到最新」悬浮按钮；切换对话或发送消息时强制回底部。
// =====================================================================

import { ref, watch, nextTick } from 'vue'
import MessageItem from './MessageItem.vue'
import { store, WELCOME_MD, sendMessage } from '../stores/app'
import { mdToHtml } from '../utils/markdown'

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

// 空对话的建议操作（点击直接发送）
const SUGGESTIONS = [
  { label: '✍️ 生成初稿', text: '生成初稿' },
  { label: '💬 把对白改口语一点', text: '把对白改口语一点' },
  { label: '⏱ 节奏改紧凑一点', text: '节奏改紧凑一点' },
  { label: '⏭ 续写下一场', text: '续写下一场，顺着当前剧情往下推进' },
  { label: '🔎 这类悬疑剧怎么设计反转？', text: '这类悬疑剧怎么设计反转？' },
]
</script>

<template>
  <div class="thread-wrap">
    <div ref="thread" class="thread" @scroll.passive="onScroll">
      <div class="thread-inner">
        <!-- 未选对话：引导创建 -->
        <div v-if="!store.messages.length && !store.convId" class="blank">
          <div class="blank-glyph" aria-hidden="true">🎬</div>
          <h3>从一部原著开始</h3>
          <p>选择左侧项目与对话，或创建你的第一个剧本项目。</p>
          <button @click="store.showNewProject = true">＋ 新建剧本</button>
        </div>

        <!-- 空对话：欢迎语 + 建议操作 -->
        <div v-else-if="!store.messages.length" class="welcome">
          <div class="hello md" v-html="mdToHtml(WELCOME_MD)"></div>
          <div class="suggestions">
            <button v-for="s in SUGGESTIONS" :key="s.text" class="ghost" @click="sendMessage(s.text)">{{ s.label }}</button>
          </div>
        </div>

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
.thread { flex: 1; overflow-y: auto; padding: 20px 24px 12px; }
.thread-inner { max-width: 820px; margin: 0 auto; }

/* 引导空态 */
.blank {
  height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center; gap: 6px;
}
.blank-glyph { font-size: 34px; margin-bottom: 4px; }
.blank h3 { margin: 0; font-size: 16px; }
.blank p { margin: 0 0 12px; color: var(--muted); font-size: 13px; }

/* 欢迎语：与助手回复一致，通栏直出 */
.hello { margin-bottom: 4px; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px; }

/* 回到最新：悬浮在对话区底部中央 */
.jump {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  z-index: 5; background: var(--panel); border: 1px solid var(--line-strong);
  box-shadow: 0 6px 20px oklch(0 0 0 / 0.35);
}
</style>
