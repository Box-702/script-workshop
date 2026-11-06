<script setup>
// =====================================================================
// ComposerCard.vue —— 输入卡片（首页与工作区共用同一套）
//
// 结构完全按首页设计：
//   ┌──────────────────────────────────────────┐
//   │ [+]  │  多行输入（可贴图、可上传）              │
//   │      │                                      │
//   │      ├──────────────────────────────────────┤
//   │      │ [胶囊][胶囊][胶囊]      状态  [开拍] │
//   └──────────────────────────────────────────┘
//
// 两处只差「放哪些胶囊」和「CTA 文案」，卡片本身只有这一份实现。
// =====================================================================

import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

const text = defineModel('text', { type: String, default: '' })

const props = defineProps({
  placeholder: { type: String, default: '描述画面，也可上传图片、视频、主体或音色，进行参考生成等。' },
  /** 产出目标胶囊（首页用；工作区已有项目，不需要） */
  goalLabel: { type: String, default: '' },
  /** 对话模型胶囊 */
  modelLabel: { type: String, default: '' },
  /** 视频规格胶囊，如「768P · 9:16」 */
  specLabel: { type: String, default: '' },
  /** 「全能参考」胶囊 */
  showReference: { type: Boolean, default: true },
  /** 上下文提示（工作区） */
  contextText: { type: String, default: '' },
  /** 阶段状态（生成中） */
  statusText: { type: String, default: '' },
  ctaText: { type: String, default: '开拍' },
  canSend: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits([
  'send', 'pick-menu', 'open-settings', 'cycle-spec', 'open-library', 'change-goal',
])

const menuOpen = ref(false)
const inputEl = ref(null)

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu(e) {
  if (menuOpen.value && e.target.closest && !e.target.closest('.cc-plus-wrap')) {
    menuOpen.value = false
  }
}

function onKeydown(e) {
  if (e.key !== 'Enter' || e.shiftKey) return
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  emit('send')
}

function autoSize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(200, el.scrollHeight) + 'px'
}

function focus() {
  inputEl.value?.focus()
}

defineExpose({ focus, closeMenu: () => (menuOpen = false) })
</script>

<template>
  <div class="cc" @click="closeMenu">
    <div class="cc-card">
      <!-- 上：＋ 按钮 + 输入 -->
      <div class="cc-top">
        <div class="cc-plus-wrap">
          <button
            class="cc-plus"
            type="button"
            aria-label="添加素材"
            :aria-expanded="menuOpen"
            :disabled="busy"
            @click.stop="toggleMenu"
          >
            <AppIcon name="plus" />
          </button>
          <Transition name="ccpop">
            <div v-if="menuOpen" class="cc-menu" role="menu">
              <slot name="menu" :close="() => (menuOpen = false)" />
            </div>
          </Transition>
        </div>

        <div class="cc-input-wrap">
          <textarea
            ref="inputEl"
            v-model="text"
            class="cc-text"
            rows="1"
            :placeholder="placeholder"
            @keydown="onKeydown"
            @input="autoSize"
            @focus="emit('focus-input')"
          ></textarea>
          <slot name="attachments" />
        </div>
      </div>

      <!-- 下：胶囊组 + 状态 + 主行动 -->
      <div class="cc-bottom">
        <div class="cc-pills">
          <slot name="pills" />
          <button
            v-if="goalLabel"
            class="chip"
            type="button"
            @click.stop="emit('change-goal')"
          >
            <AppIcon name="film" />
            <span>{{ goalLabel }}</span>
            <AppIcon name="chevron-down" class="cc-chev" />
          </button>
          <button
            v-if="modelLabel"
            class="chip"
            type="button"
            title="当前对话模型 · 点击在设置中更换"
            @click.stop="emit('open-settings')"
          >
            <AppIcon name="sparkle" />
            <span>{{ modelLabel }}</span>
            <AppIcon name="chevron-down" class="cc-chev" />
          </button>
          <button
            v-if="showReference"
            class="chip"
            type="button"
            @click.stop="emit('open-library')"
          >
            <AppIcon name="folder" />
            <span>全能参考</span>
            <AppIcon name="chevron-down" class="cc-chev" />
          </button>
          <button
            v-if="specLabel"
            class="chip"
            type="button"
            @click.stop="emit('cycle-spec')"
          >
            <AppIcon name="play" />
            <span>{{ specLabel }}</span>
            <AppIcon name="chevron-down" class="cc-chev" />
          </button>
          <span v-if="contextText" class="cc-context">{{ contextText }}</span>
        </div>

        <div class="cc-right">
          <Transition name="ccfade">
            <span v-if="statusText" class="cc-stage" role="status" aria-live="polite">
              <span class="cc-pulse" aria-hidden="true"></span>{{ statusText }}
            </span>
          </Transition>
          <button
            class="cta cc-cta"
            type="button"
            :disabled="!canSend"
            @click.stop="emit('send')"
          >{{ ctaText }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cc { width: 100%; }

.cc-card {
  position: relative;
  border-radius: var(--radius-card);
  padding: 14px 14px 12px;
  background: rgba(255, 255, 255, 0.055);
  border: 1px solid var(--line);
  backdrop-filter: var(--glass);
  -webkit-backdrop-filter: var(--glass);
  box-shadow: var(--shadow-3);
  transition: border-color 0.18s ease, background 0.18s ease;
}

.cc-card:focus-within {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.075);
}

.cc-top { display: flex; align-items: flex-start; gap: 12px; }

.cc-plus-wrap { position: relative; flex: none; }

.cc-plus {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.07);
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.cc-plus:hover:not(:disabled) { background: rgba(255, 255, 255, 0.17); color: #fff; }
.cc-plus:disabled { opacity: 0.4; cursor: not-allowed; }

.cc-menu {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  min-width: 190px;
  padding: 6px;
  border-radius: 12px;
  background: rgba(22, 22, 28, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: var(--shadow-3);
  z-index: 30;
}

.cc-input-wrap { flex: 1; min-width: 0; padding-top: 14px; }

.cc-text {
  width: 100%;
  min-height: 84px;
  max-height: 200px;
  resize: none;
  border: 0;
  outline: 0;
  background: transparent;
  color: rgba(255, 255, 255, 0.94);
  font-size: 14px;
  line-height: 1.65;
  font-family: inherit;
}

.cc-text::placeholder { color: rgba(255, 255, 255, 0.34); }

.cc-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.cc-pills {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.cc-chev { opacity: 0.5; }

.cc-context {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cc-right { display: flex; align-items: center; gap: 10px; flex: none; }

.cc-stage {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 550;
  white-space: nowrap;
}

.cc-pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  animation: ccpulse 1.4s ease-in-out infinite;
}

@keyframes ccpulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.cc-cta {
  min-width: 88px;
  height: 38px;
  padding: 0 20px;
  font-size: 14px;
  border-radius: 9px;
}

.ccpop-enter-active,
.ccpop-leave-active { transition: opacity 0.14s ease, transform 0.14s ease; }
.ccpop-enter-from,
.ccpop-leave-to { opacity: 0; transform: translateY(6px); }

.ccfade-enter-active,
.ccfade-leave-active { transition: opacity 0.18s ease; }
.ccfade-enter-from,
.ccfade-leave-to { opacity: 0; }
</style>
