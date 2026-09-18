<template>
  <div class="chat-list">
    <div class="chat-header">
      <div>
        <span class="chat-eyebrow">WORKSPACE</span>
        <span class="chat-title">对话空间</span>
      </div>
      <button class="btn-new" @click="onNew" title="新建聊天" aria-label="新建聊天">+</button>
    </div>

    <!-- 全局对话 -->
    <div class="conv-section">
      <div
        v-for="conv in globalConvs"
        :key="conv.id"
        :class="['conv-item', { active: isActive(null, conv.id) }]"
        @click="onSelect(null, conv.id)"
      >
        <span class="conv-icon">01</span>
        <span class="conv-name" v-if="editingId !== conv.id">{{ conv.title }}</span>
        <input
          v-else
          class="conv-edit"
          v-model="editTitle"
          @blur="onRename(null, conv.id)"
          @keydown.enter="onRename(null, conv.id)"
          @keydown.escape="editingId = null"
          ref="editInput"
        />
        <span class="conv-count" v-if="conv.user_message_count">{{ conv.user_message_count }}</span>
        <span class="conv-actions">
          <button class="btn-tiny" @click.stop="startRename(conv)" title="重命名" aria-label="重命名">✎</button>
          <button class="btn-tiny" @click.stop="onDelete(null, conv.id)" title="删除" aria-label="删除">×</button>
        </span>
      </div>
      <div v-if="!globalConvs.length" class="conv-empty">
        还没有对话，点击 + 开始
      </div>
    </div>

    <!-- 项目内对话（按项目分组） -->
    <div v-for="p in projects" :key="p.id" class="conv-group">
      <div class="group-header" @click="toggleExpand(p.id)">
        <span class="expand-icon">{{ expanded[p.id] ? '▼' : '▶' }}</span>
        <span class="group-name">{{ p.title }}</span>
      </div>
      <div v-if="expanded[p.id]" class="group-children">
        <div
          v-for="conv in (convMap[p.id] || [])"
          :key="conv.id"
          :class="['conv-item', { active: isActive(p.id, conv.id) }]"
          @click="onSelect(p.id, conv.id)"
        >
          <span class="conv-icon">02</span>
          <span class="conv-name" v-if="editingId !== conv.id">{{ conv.title }}</span>
          <input
            v-else
            class="conv-edit"
            v-model="editTitle"
            @blur="onRename(p.id, conv.id)"
            @keydown.enter="onRename(p.id, conv.id)"
            @keydown.escape="editingId = null"
          />
          <span class="conv-actions">
            <button class="btn-tiny" @click.stop="startRename(conv)" title="重命名" aria-label="重命名">✎</button>
            <button class="btn-tiny" @click.stop="onDelete(p.id, conv.id)" title="删除" aria-label="删除">×</button>
          </span>
        </div>
        <button class="conv-add" @click="onNewProject(p.id)">＋ 新对话</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { store, newGlobalConversation, selectGlobalConversation, loadGlobalConversations, newConversation, selectConversation, setConversationTitle, deleteConversation, loadConversations, toggleProject } from '../stores/app.js'

const globalConvs = computed(() => store.globalConvs)
const projects = computed(() => store.projects)
const convMap = computed(() => store.convMap)
const expanded = computed(() => store.expanded)

const editingId = ref(null)
const editTitle = ref('')
const editInput = ref(null)

function isActive(pid, convId) {
  return store.convId === convId && store.pid === pid
}

function onNew() {
  newGlobalConversation()
}

function onSelect(pid, convId) {
  if (pid) {
    selectConversation(pid, convId)
  } else {
    selectGlobalConversation(convId)
  }
}

function onNewProject(pid) {
  newConversation(pid)
}

function toggleExpand(pid) {
  toggleProject(pid)
}

function startRename(conv) {
  editingId.value = conv.id
  editTitle.value = conv.title
  nextTick(() => editInput.value?.focus())
}

function onRename(pid, convId) {
  const t = editTitle.value.trim()
  if (t && t !== store.globalConvs.find(c => c.id === convId)?.title) {
    setConversationTitle(pid, convId, t)
    if (!pid) loadGlobalConversations()
  }
  editingId.value = null
}

function onDelete(pid, convId) {
  if (!confirm('确定删除这个对话？')) return
  deleteConversation(convId, pid)
}
</script>

<style scoped>
.chat-list { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.chat-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 13px 14px 12px; border-bottom: 1px solid var(--line);
}
.chat-header > div { display: flex; flex-direction: column; gap: 4px; }
.chat-eyebrow { color: var(--gold); font: 700 9px/1 var(--mono); letter-spacing: .14em; }
.chat-title { font-size: 13px; font-weight: 650; color: var(--ink); }
.btn-new {
  width: 26px; height: 26px; border-radius: 7px; border: 1px solid var(--line);
  background: transparent; color: var(--muted); cursor: pointer; font-size: 15px;
  display: flex; align-items: center; justify-content: center;
}
.btn-new:hover { border-color: var(--gold); color: var(--gold); background: var(--gold-soft); }

.conv-section { flex: 1; overflow-y: auto; padding: 4px 0; }

.conv-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 12px;
  cursor: pointer; font-size: 12px; transition: background .14s, color .14s;
}
.conv-item:hover { background: color-mix(in oklch, var(--ink) 4%, transparent); }
.conv-item.active { background: color-mix(in oklch, var(--gold) 8%, transparent); color: var(--ink); }
.conv-icon { color: var(--dim); font: 9px/1 var(--mono); flex-shrink: 0; }
.conv-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-count {
  font-size: 10px; color: var(--text2, #666); background: rgba(255,255,255,.05);
  padding: 1px 5px; border-radius: 3px;
}
.conv-actions { display: flex; gap: 2px; opacity: 0; pointer-events: none; transition: opacity 140ms var(--ease); }
.conv-item:hover .conv-actions, .conv-item:focus-within .conv-actions { opacity: 1; pointer-events: auto; }
.btn-tiny {
  background: none; border: none; cursor: pointer; font-size: 10px; padding: 2px;
  opacity: .6; color: var(--muted);
}
.btn-tiny:hover { opacity: 1; }
.conv-edit {
  flex: 1; background: var(--code-bg, #111); border: 1px solid var(--gold, #e94560);
  border-radius: 3px; color: var(--text, #eee); font-size: 12px; padding: 2px 4px; outline: none;
}
.conv-empty { padding: 16px 12px; font-size: 11px; color: var(--text2, #555); text-align: center; }
.conv-add {
  display: block; width: 100%; padding: 5px 12px 6px 30px; font-size: 11px; color: var(--dim);
  cursor: pointer; opacity: 0; transition: opacity .15s, color .15s; text-align: left;
  background: transparent; border: 0; font-weight: 500;
}
.conv-group:hover .conv-add { opacity: 1; }
.conv-add:hover { color: var(--gold); }

.conv-group { border-top: 1px solid rgba(255,255,255,.03); }
.group-header {
  display: flex; align-items: center; gap: 6px; padding: 6px 12px;
  cursor: pointer; font-size: 12px; font-weight: 600;
}
.group-header:hover { background: rgba(255,255,255,.03); }
.expand-icon { font-size: 9px; color: var(--gold); }
.group-name { flex: 1; }
.group-children { padding-left: 8px; }
</style>
