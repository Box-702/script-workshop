<script setup>
// =====================================================================
// ChatComposer.vue —— 底部输入区（Codex 式）
//
// 结构：圆角容器 = 文本域 + 底部工具行
//   工具行左：「＋」新建剧本 + 上下文提示
//   工具行右：流式时「生成中」呼吸点，发送按钮（右箭头）
// =====================================================================

import { ref, computed, watch, nextTick } from 'vue'
import { store, sendMessage } from '../stores/app'

const input = ref(null)
const text = ref('')

const canSend = computed(() => !!text.value.trim() && !store.streaming)

function send() {
  const t = text.value.trim()
  if (!t || store.streaming) return
  text.value = ''
  input.value.style.height = 'auto'
  sendMessage(t)
}

function onKeydown(e) {
  if (e.key !== 'Enter' || e.shiftKey) return
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  send()
}

function autoSize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(160, el.scrollHeight) + 'px'
}

watch(() => store.convId, () => nextTick(() => input.value?.focus()))
</script>

<template>
  <div class="composer">
    <div class="input-box" @click="input?.focus()">
      <textarea
        ref="input"
        v-model="text"
        rows="1"
        placeholder="说点什么…"
        @keydown="onKeydown"
        @input="autoSize"
      ></textarea>
      <div class="toolbar">
        <div class="toolbar-left">
          <button class="plus" title="新建剧本" @click.stop="store.showNewProject = true">＋</button>
          <span v-if="store.hint" class="hint">{{ store.hint }}</span>
        </div>
        <div class="toolbar-right">
          <span v-if="store.streaming" class="streaming"><span class="pulse"></span>生成中</span>
          <button class="send" :class="{ ready: canSend }" :disabled="!canSend" @click.stop="send">
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M10 3L5 8l5 5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer { padding: 8px 20px 16px; background: transparent; }

/* 圆角容器：文本域 + 工具行 */
.input-box {
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  padding: 8px 10px 6px; cursor: text;
  max-width: 820px; margin: 0 auto;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.input-box:focus-within {
  border-color: color-mix(in oklch, var(--accent) 35%, var(--line));
  box-shadow: 0 0 0 3px var(--accent-soft);
}
textarea {
  display: block; width: 100%; min-height: 20px; max-height: 160px; line-height: 1.5;
  background: transparent; border: none; padding: 2px 4px;
  font-size: 13.5px; color: var(--ink); resize: none;
  overflow-y: auto;
}
textarea::placeholder { color: var(--dim); }
textarea:focus { outline: none; box-shadow: none; border: none; }
textarea:focus-visible { outline: none; }

/* 工具行：固定高度，与文本域分开 */
.toolbar { display: flex; align-items: center; gap: 6px; padding: 4px 2px 0; min-height: 32px; }
.toolbar-left { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.plus {
  width: 28px; height: 28px; padding: 0; border-radius: 8px; flex: none;
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  font-size: 15px; font-weight: 500; line-height: 1;
  display: inline-grid; place-items: center;
}
.plus:hover { color: var(--ink); border-color: var(--line-strong); background: color-mix(in oklch, var(--ink) 6%, transparent); }
.hint { color: var(--dim); font-size: 11.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex: none; }
.streaming { display: inline-flex; align-items: center; gap: 5px; color: var(--muted); font-size: 11.5px; }
.pulse { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: pulse 1.1s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.25; } 50% { opacity: 1; } }

/* 发送按钮 */
.send {
  width: 28px; height: 28px; padding: 0; border-radius: 8px;
  background: transparent; color: var(--dim);
  display: inline-grid; place-items: center; flex: none;
}
.send svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.send.ready { background: var(--accent); color: var(--on-accent); }
.send.ready:hover:not(:disabled) { background: var(--accent-hover); }
.send:disabled { opacity: 0.45; cursor: default; }
</style>
