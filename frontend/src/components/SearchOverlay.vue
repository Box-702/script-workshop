<script setup>
// =====================================================================
// SearchOverlay.vue —— 剧本内搜索（Ctrl+F）
//
// 浮动搜索条：输入关键词后高亮匹配的场景/节拍，
// Enter 跳转下一个，Shift+Enter 跳转上一个。
// =====================================================================

import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { store } from '../stores/app'

const open = ref(false)
const query = ref('')
const inputRef = ref(null)
const currentIdx = ref(0)

// 搜索结果：在 viewerScript 的场景/节拍中查找
const results = computed(() => {
  const q = query.value.toLowerCase().trim()
  if (!q || !store.viewerScript) return []
  const hits = []
  for (const sc of store.viewerScript.scenes || []) {
    // 场景标题
    if ((sc.title || '').toLowerCase().includes(q)) {
      hits.push({ type: 'scene', id: sc.id, title: sc.title, field: '标题' })
    }
    // 场景目的
    if ((sc.purpose || '').toLowerCase().includes(q)) {
      hits.push({ type: 'scene', id: sc.id, title: sc.title, field: '目的' })
    }
    // 节拍
    for (const b of sc.beats || []) {
      const text = b.text || b.line || ''
      if (text.toLowerCase().includes(q)) {
        hits.push({ type: 'beat', id: b.id, sceneId: sc.id, sceneTitle: sc.title, text: text.slice(0, 60) })
      }
    }
  }
  return hits
})

const total = computed(() => results.value.length)
const current = computed(() => results.value[currentIdx.value] || null)

function openSearch() {
  open.value = true
  nextTick(() => inputRef.value?.focus())
}
function closeSearch() {
  open.value = false
  query.value = ''
  currentIdx.value = 0
}
function next() {
  if (!total.value) return
  currentIdx.value = (currentIdx.value + 1) % total.value
}
function prev() {
  if (!total.value) return
  currentIdx.value = (currentIdx.value - 1 + total.value) % total.value
}
function onKeydown(e) {
  if (e.key === 'Escape') closeSearch()
  else if (e.key === 'Enter') { e.shiftKey ? prev() : next() }
}

// 全局 Ctrl+F
function globalKey(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    if (open.value) inputRef.value?.focus()
    else openSearch()
  }
}
onMounted(() => window.addEventListener('keydown', globalKey))
onUnmounted(() => window.removeEventListener('keydown', globalKey))

// 搜索时重置索引
watch(query, () => { currentIdx.value = 0 })

defineExpose({ openSearch, closeSearch })
</script>

<template>
  <Teleport to="body">
    <Transition name="search-slide">
      <div v-if="open" class="search-bar" role="search" aria-label="剧本搜索" @keydown="onKeydown">
        <span class="search-icon">⌕</span>
        <input
          ref="inputRef"
          v-model="query"
          class="search-input"
          placeholder="搜索场景、节拍、对白…"
          aria-label="搜索关键词"
          spellcheck="false"
          autocomplete="off"
        />
        <span v-if="query" class="search-count">
          {{ total ? currentIdx + 1 : 0 }} / {{ total }}
        </span>
        <button class="search-btn" :disabled="!total" aria-label="上一个" @click="prev">‹</button>
        <button class="search-btn" :disabled="!total" aria-label="下一个" @click="next">›</button>
        <button class="search-btn search-close" aria-label="关闭搜索" @click="closeSearch">✕</button>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.search-bar {
  position: fixed; top: 52px; right: 16px; z-index: 8000;
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; border-radius: 10px;
  background: var(--panel); border: 1px solid var(--line-strong);
  box-shadow: 0 8px 32px oklch(0 0 0 / 0.4);
  animation: search-slide 200ms var(--ease) both;
}
@keyframes search-slide {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.search-icon { color: var(--gold); font: 700 18px/1 var(--mono); flex: none; }
.search-input {
  width: 220px; padding: 3px 8px; border-radius: 6px;
  background: var(--code-bg); border: 1px solid var(--line);
  font-size: 12.5px; color: var(--ink); outline: none;
}
.search-input:focus { border-color: color-mix(in oklch, var(--gold) 40%, var(--line)); }
.search-count { font-size: 11px; color: var(--dim); font-variant-numeric: tabular-nums; flex: none; min-width: 36px; text-align: center; }
.search-btn {
  width: 24px; height: 24px; padding: 0; border-radius: 6px;
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  display: grid; place-items: center; font-size: 14px; cursor: pointer;
}
.search-btn:hover:not(:disabled) { color: var(--ink); border-color: var(--line-strong); }
.search-btn:disabled { opacity: 0.3; }
.search-close { border: none; font-size: 12px; }
</style>
