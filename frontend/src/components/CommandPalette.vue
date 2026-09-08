<script setup>
// =====================================================================
// CommandPalette.vue —— 命令面板（Ctrl+K / Cmd+K）
//
// 借鉴 Linear/Raycast 的命令面板：模糊搜索项目、对话、命令，
// 键盘优先导航，替代传统的菜单/按钮操作。
// =====================================================================

import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { store, selectProject, selectConversation, showView, toggleRightPanel } from '../stores/app'

const open = ref(false)
const query = ref('')
const selectedIdx = ref(0)
const inputRef = ref(null)

// ---- 快捷命令定义 ----
const COMMANDS = [
  { id: 'new', label: '新建剧本', hint: '创建新的剧本项目', icon: '📝', category: '操作' },
  { id: 'generate', label: '生成初稿', hint: '为当前项目生成剧本初稿', icon: '✨', category: '操作', needsProject: true },
  { id: 'adapt', label: '改编剧本', hint: '对当前项目发起改编', icon: '🔄', category: '操作', needsProject: true },
  { id: 'analyze', label: '分析场景', hint: '启动场景分析子代理', icon: '📊', category: '操作', needsProject: true },
  { id: 'check-style', label: '检查风格', hint: '检查全剧风格一致性', icon: '🎯', category: '操作', needsProject: true },
  { id: 'polish', label: '润色对白', hint: '启动对白润色子代理', icon: '💬', category: '操作', needsProject: true },
  { id: 'editor', label: '剧本编辑器', hint: '切换到剧本编辑面板', icon: '📄', category: '面板' },
  { id: 'agents', label: 'Agent 任务', hint: '查看后台子代理任务', icon: '🤖', category: '面板' },
  { id: 'toggle-panel', label: '切换右侧面板', hint: '打开/关闭右侧 Inspector', icon: '◧', category: '面板' },
]

// ---- 构建搜索条目 ----
const items = computed(() => {
  const result = []
  const q = query.value.toLowerCase().trim()

  // 项目
  for (const p of store.projects) {
    if (q && !p.title.toLowerCase().includes(q)) continue
    result.push({
      id: `proj:${p.id}`,
      label: p.title,
      hint: `${p.version_count} 个版本`,
      icon: '📁',
      category: '项目',
      action: () => selectProject(p.id),
    })
  }

  // 当前项目的对话
  if (store.pid) {
    const convs = store.convMap[store.pid] || []
    for (const c of convs) {
      if (q && !c.title.toLowerCase().includes(q)) continue
      result.push({
        id: `conv:${c.id}`,
        label: c.title,
        hint: '对话',
        icon: '💬',
        category: '对话',
        action: () => selectConversation(store.pid, c.id),
      })
    }
  }

  // 命令
  for (const cmd of COMMANDS) {
    if (cmd.needsProject && !store.pid) continue
    if (q && !cmd.label.toLowerCase().includes(q) && !cmd.hint.toLowerCase().includes(q)) continue
    result.push({
      ...cmd,
      action: () => runCommand(cmd.id),
    })
  }

  return result
})

// ---- 执行命令 ----
function runCommand(id) {
  closePalette()
  switch (id) {
    case 'new':
      store.showNewProject = true
      break
    case 'generate':
      if (store.pid && store.convId) {
        store.draft = '生成初稿'
        store.draftSeq++
      }
      break
    case 'adapt':
      if (store.pid && store.convId) {
        store.draft = '请对当前剧本进行改编：'
        store.draftSeq++
      }
      break
    case 'analyze':
      if (store.pid && store.convId) {
        store.draft = '分析场景结构'
        store.draftSeq++
      }
      break
    case 'check-style':
      if (store.pid && store.convId) {
        store.draft = '检查风格一致性'
        store.draftSeq++
      }
      break
    case 'polish':
      if (store.pid && store.convId) {
        store.draft = '润色对白'
        store.draftSeq++
      }
      break
    case 'editor':
      if (!store.rightOpen) toggleRightPanel()
      showView('editor')
      break
    case 'agents':
      if (!store.rightOpen) toggleRightPanel()
      showView('agents')
      break
    case 'toggle-panel':
      toggleRightPanel()
      break
  }
}

// ---- 键盘导航 ----
function onKeydown(e) {
  if (e.key === 'Escape') {
    closePalette()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIdx.value = Math.min(selectedIdx.value + 1, items.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIdx.value = Math.max(selectedIdx.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const item = items.value[selectedIdx.value]
    if (item?.action) item.action()
  }
}

// ---- 打开/关闭 ----
function openPalette() {
  open.value = true
  query.value = ''
  selectedIdx.value = 0
  nextTick(() => inputRef.value?.focus())
}

function closePalette() {
  open.value = false
  query.value = ''
}

// 全局快捷键
function globalKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    if (open.value) closePalette()
    else openPalette()
  }
}

onMounted(() => window.addEventListener('keydown', globalKeydown))
onUnmounted(() => window.removeEventListener('keydown', globalKeydown))

// 搜索时重置选中
watch(query, () => { selectedIdx.value = 0 })

// 暴露给父组件
defineExpose({ openPalette, closePalette })
</script>

<template>
  <Teleport to="body">
    <Transition name="cp">
      <div v-if="open" class="cp-overlay" role="dialog" aria-modal="true" aria-label="命令面板" @mousedown.self="closePalette">
        <div class="cp" @keydown="onKeydown">
          <div class="cp-input-wrap">
            <span class="cp-icon">⌘</span>
            <input
              ref="inputRef"
              v-model="query"
              class="cp-input"
              placeholder="搜索项目、对话、命令…"
              aria-label="搜索命令"
              spellcheck="false"
              autocomplete="off"
            />
            <kbd class="cp-kbd">Esc</kbd>
          </div>
          <div v-if="items.length" class="cp-list">
            <template v-for="(item, i) in items" :key="item.id">
              <div v-if="i > 0 && items[i].category !== items[i - 1].category" class="cp-divider" />
              <div
                class="cp-item"
                :class="{ active: i === selectedIdx }"
                @mousedown.prevent="item.action?.()"
                @mouseenter="selectedIdx = i"
              >
                <span class="cp-item-icon">{{ item.icon }}</span>
                <span class="cp-item-label">{{ item.label }}</span>
                <span class="cp-item-hint">{{ item.hint }}</span>
              </div>
            </template>
          </div>
          <div v-else class="cp-empty">没有匹配的结果</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cp-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: oklch(0 0 0 / 0.45); backdrop-filter: blur(4px);
  display: flex; justify-content: center; padding-top: min(20vh, 160px);
}
.cp {
  width: min(560px, 90vw); max-height: 420px;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 14px; box-shadow: 0 24px 80px oklch(0 0 0 / 0.5);
  display: flex; flex-direction: column; overflow: hidden;
}
.cp-input-wrap {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; border-bottom: 1px solid var(--line);
}
.cp-icon { font-size: 14px; color: var(--dim); flex: none; }
.cp-input {
  flex: 1; background: transparent; border: none; outline: none;
  font-size: 15px; color: var(--ink); font-family: inherit;
}
.cp-input::placeholder { color: var(--dim); }
.cp-kbd {
  font-size: 10px; font-family: var(--mono); color: var(--dim);
  background: var(--panel2); border: 1px solid var(--line);
  border-radius: 4px; padding: 1px 5px; flex: none;
}
.cp-list { overflow-y: auto; padding: 6px; }
.cp-divider {
  height: 1px; background: var(--line); margin: 4px 8px; opacity: 0.5;
}
.cp-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
  transition: background var(--dur) var(--ease);
}
.cp-item.active { background: var(--select); }
.cp-item-icon { font-size: 15px; flex: none; width: 22px; text-align: center; }
.cp-item-label { font-size: 13px; font-weight: 500; color: var(--ink); flex: none; }
.cp-item-hint { font-size: 11.5px; color: var(--dim); flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: right; }
.cp-empty { padding: 20px; text-align: center; color: var(--dim); font-size: 12px; }

/* 入场/退场动画 */
.cp-enter-active { transition: opacity var(--dur) var(--ease); }
.cp-leave-active { transition: opacity 100ms ease-in; }
.cp-enter-from, .cp-leave-to { opacity: 0; }
.cp-enter-active .cp { animation: cp-slide-up var(--dur) var(--ease); }
@keyframes cp-slide-up {
  from { transform: translateY(-12px) scale(0.97); opacity: 0; }
  to { transform: translateY(0) scale(1); opacity: 1; }
}
</style>
