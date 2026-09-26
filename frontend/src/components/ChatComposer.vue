<script setup>
// =====================================================================
// ChatComposer.vue —— 底部输入区
//
// 结构：圆角容器 = 文本域 + 底部工具行
//   工具行左：「＋ 导入文档」（txt/md/docx/pdf）+ 上下文提示
//   工具行右：生成中的阶段状态条（aria-live）+ 发送按钮「开始生成」
// 交互：Enter 发送 / Shift+Enter 换行（含输入法 composing 保护）；
//       所有点击目标 ≥44px；发送按钮有 hover/active/disabled。
// =====================================================================

import { ref, computed, watch, nextTick } from 'vue'
import { store, sendMessage, focusComposer } from '../stores/app'

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

// 开始页主按钮 / 编辑态空态的「输入我的想法」：聚焦输入框
watch(() => store.focusSeq, () => nextTick(() => input.value?.focus()))

watch(() => store.convId, () => nextTick(() => input.value?.focus()))

// 开始页示例模板把文本填进输入框（不自动发送，由用户确认后发出）。
watch(() => store.draftSeq, () => {
  if (!store.draft) return
  text.value = store.draft
  nextTick(() => {
    const el = input.value
    if (!el) return
    el.focus()
    el.style.height = 'auto'
    el.style.height = Math.min(160, el.scrollHeight) + 'px'
  })
})
</script>

<template>
  <div class="composer">
    <div class="input-box" @click="input?.focus()">
      <textarea
        ref="input"
        v-model="text"
        rows="1"
        placeholder="描述你的故事想法，例如：一个失去记忆的出租车司机，在雨夜接到未来的自己。"
        aria-label="描述你的故事想法"
        @keydown="onKeydown"
        @input="autoSize"
      ></textarea>
      <div class="toolbar">
        <div class="toolbar-left">
          <button
            class="plus"
            title="导入文档（.txt / .md / .docx / .pdf）"
            aria-label="导入文档"
            @click.stop="store.showNewProject = true"
          >＋</button>
          <span class="composer-context">
            <span class="context-dot" :class="{ active: store.pid }"></span>
            <span v-if="store.hint" class="hint">{{ store.hint }}</span>
            <span v-else>{{ store.pid ? '准备好继续创作' : '导入文档，或直接从一句话开始' }}</span>
          </span>
        </div>
        <div class="toolbar-right">
          <!-- 阶段状态条：生成过程中展示当前阶段 -->
          <Transition name="stagefade">
            <span
              v-if="store.streaming"
              class="stage"
              role="status"
              aria-live="polite"
            >
              <span class="pulse" aria-hidden="true"></span>{{ store.streamingStage || '正在处理' }}
            </span>
          </Transition>
          <button
            class="send"
            :class="{ ready: canSend }"
            :disabled="!canSend"
            :aria-label="canSend ? '开始生成' : '输入内容后开始生成'"
            title="开始生成（Enter）"
            @click.stop="send"
          >
            <span aria-hidden="true">↑</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer { padding: var(--space-3) clamp(var(--space-4), 3vw, var(--space-6)) var(--space-4); background: transparent; }

/* 圆角容器：文本域 + 工具行（焦点光环走 --focus-ring 语义） */
.input-box {
  background: var(--panel);
  border: 1px solid var(--line); border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3) 7px; cursor: text;
  max-width: 900px; margin: 0 auto;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.input-box:focus-within {
  border-color: color-mix(in oklch, var(--gold) 40%, var(--line));
  box-shadow: 0 0 0 2px color-mix(in oklch, var(--gold) 14%, transparent);
}
textarea {
  display: block; width: 100%; min-height: 24px; max-height: 160px;
  line-height: var(--lh-body);
  background: transparent; border: none; padding: 2px 4px;
  font-size: var(--fs-lg); color: var(--ink); resize: none; font-family: var(--font-kai);
  overflow-y: auto;
}
textarea::placeholder { color: var(--dim); transition: color var(--dur) var(--ease); }
textarea:focus { outline: none; box-shadow: none; border: none; }
textarea:focus-visible { outline: none; }

/* 工具行 */
.toolbar { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) 2px 0; min-height: 44px; }
.toolbar-left { display: flex; align-items: center; gap: var(--space-2); flex: 1; min-width: 0; }
/* ＋ 导入文档：可视 36px，命中区扩到 44px */
.plus {
  position: relative;
  width: 36px; height: 36px; padding: 0; border-radius: var(--radius-md); flex: none;
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  font-size: 16px; font-weight: 500; line-height: 1;
  display: inline-grid; place-items: center;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}
.plus::after { content: ''; position: absolute; inset: -4px; border-radius: inherit; }
.plus:hover:not(:disabled) { color: var(--ink); border-color: var(--line-strong); background: color-mix(in oklch, var(--ink) 6%, transparent); }
.plus:active:not(:disabled) { background: color-mix(in oklch, var(--ink) 10%, transparent); }
.hint { color: var(--dim); font-size: var(--fs-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.composer-context { min-width: 0; display: inline-flex; align-items: center; gap: 7px; color: var(--dim); font-size: var(--fs-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.context-dot { width: 6px; height: 6px; flex: none; border-radius: 50%; background: var(--dim); }
.context-dot.active { background: var(--cyan); box-shadow: 0 0 10px color-mix(in oklch, var(--cyan) 60%, transparent); }
.toolbar-right { display: flex; align-items: center; gap: var(--space-2); flex: none; }

/* 阶段状态条 */
.stage {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--gold); font-size: var(--fs-sm); font-weight: 550;
  white-space: nowrap;
}
.pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--gold); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.3; transform: scale(0.9); } 50% { opacity: 1; transform: scale(1.1); } }
.stagefade-enter-active, .stagefade-leave-active { transition: opacity var(--dur-slow) var(--ease); }
.stagefade-enter-from, .stagefade-leave-to { opacity: 0; }

/* 发送按钮「开始生成」：44×44 命中区 */
.send {
  position: relative;
  width: 44px; height: 44px; padding: 0; border-radius: var(--radius-md);
  background: transparent; color: var(--dim);
  border: 1px solid transparent;
  display: inline-grid; place-items: center; flex: none;
  transition: background-color 200ms var(--ease), color 200ms var(--ease), border-color 200ms var(--ease);
}
.send > span { font-size: 20px; line-height: 1; transform: translateY(-1px); }
.send.ready {
  background: var(--gold);
  color: var(--on-accent);
}
.send.ready:hover:not(:disabled) { background: var(--accent-hover); }
.send.ready:active:not(:disabled) { background: color-mix(in oklch, var(--gold) 86%, black); }
.send:disabled { opacity: 0.45; cursor: default; }
</style>
