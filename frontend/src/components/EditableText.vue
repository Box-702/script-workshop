<script setup>
// =====================================================================
// EditableText.vue —— 可原位编辑的文本（contenteditable 封装）
//
// 用 contenteditable 的「无框、随内容换行撑高」替代输入框，让剧本更像
// 「一部可以直接改的书稿」而非一堆表单。父组件负责视觉角色（标题/动作/
// 角色名/台词…），本组件只提供编辑行为：
//   - input 实时写回 modelValue；blur 时 trim 并再写回；
//   - singleLine 时 Enter 直接失焦；
//   - 空内容时用 data-ph 显示占位文案。
// =====================================================================

import { ref, onMounted } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  ph: { type: String, default: '' },
  singleLine: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const el = ref(null)

// 只在挂载时把初值写进 DOM（避免每次响应式重渲染重置光标）。
onMounted(() => { if (el.value) el.value.innerText = String(props.modelValue ?? '') })

function onInput() { emit('update:modelValue', el.value.innerText) }

function onBlur() {
  const v = el.value.innerText.trim()
  el.value.innerText = v
  emit('update:modelValue', v)
}

function onKeydown(e) {
  if (props.singleLine && e.key === 'Enter') { e.preventDefault(); el.value.blur() }
}
</script>

<template>
  <span
    ref="el"
    class="et"
    contenteditable="true"
    :data-ph="ph"
    spellcheck="false"
    @input="onInput"
    @blur="onBlur"
    @keydown="onKeydown"
  ></span>
</template>

<style scoped>
.et { white-space: pre-wrap; word-break: break-word; outline: none; }
.et:empty::before { content: attr(data-ph); color: var(--dim); }
.et:focus {
  background: color-mix(in oklch, var(--ink) 5%, transparent);
  border-radius: 4px;
  box-shadow: 0 0 0 1px color-mix(in oklch, var(--accent) 25%, transparent);
}
</style>
