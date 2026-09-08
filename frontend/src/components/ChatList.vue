<template>
  <div class="chat-list">
    <div class="chat-header">
      <span class="chat-title">💬 聊天</span>
      <button class="btn-new" @click="onNew" title="新建聊天">+</button>
    </div>

    <!-- 全局对话 -->
    <div class="conv-section">
      <div
        v-for="conv in globalConvs"
        :key="conv.id"
        :class="['conv-item', { active: isActive(null, conv.id) }]"
        @click="onSelect(null, conv.id)"
      >
        <span class="conv-icon">💬</span>
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
          <button class="btn-tiny" @click.stop="startRename(conv)" title="重命名">✏️</button>
          <button class="btn-tiny" @click.stop="onDelete(null, conv.id)" title="删除">🗑</button>
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
        <span class="group-name">📁 {{ p.title }}</span>
      </div>
      <div v-if="expanded[p.id]" class="group-children">
        <div
          v-for="conv in (convMap[p.id] || [])"
          :key="conv.id"
          :class="['conv-item', { active: isActive(p.id, conv.id) }]"
          @click="onSelect(p.id, conv.id)"
        >
          <span class="conv-icon">📄</span>
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
            <button class="btn-tiny" @click.stop="startRename(conv)" title="重命名">✏️</button>
            <button class="btn-tiny" @click.stop="onDelete(p.id, conv.id)" title="删除">🗑</button>
          </span>
        </div>
        <div class="conv-add" @click="onNewProject(p.id)">+ 新对话</div>
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
  padding: 10px 12px; border-bottom: 1px solid var(--border, #222);
}
.chat-title { font-size: 13px; font-weight: 600; }
.btn-new {
  width: 24px; height: 24px; border-radius: 6px; border: 1px solid var(--border, #333);
  background: none; color: var(--text, #eee); cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}
.btn-new:hover { border-color: var(--gold, #e94560); color: var(--gold, #e94560); }

.conv-section { flex: 1; overflow-y: auto; padding: 4px 0; }

.conv-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 12px;
  cursor: pointer; font-size: 12px; transition: background .1s;
}
.conv-item:hover { background: rgba(255,255,255,.03); }
.conv-item.active { background: rgba(233,69,96,.08); border-left: 2px solid var(--gold, #e94560); }
.conv-icon { font-size: 11px; flex-shrink: 0; }
.conv-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-count {
  font-size: 10px; color: var(--text2, #666); background: rgba(255,255,255,.05);
  padding: 1px 5px; border-radius: 3px;
}
.conv-actions { display: none; gap: 2px; }
.conv-item:hover .conv-actions { display: flex; }
.btn-tiny {
  background: none; border: none; cursor: pointer; font-size: 10px; padding: 2px;
  opacity: .6;
}
.btn-tiny:hover { opacity: 1; }
.conv-edit {
  flex: 1; background: var(--code-bg, #111); border: 1px solid var(--gold, #e94560);
  border-radius: 3px; color: var(--text, #eee); font-size: 12px; padding: 2px 4px; outline: none;
}
.conv-empty { padding: 16px 12px; font-size: 11px; color: var(--text2, #555); text-align: center; }
.conv-add {
  padding: 4px 12px 4px 28px; font-size: 11px; color: var(--text2, #666);
  cursor: pointer; opacity: 0; transition: opacity .15s;
}
.conv-group:hover .conv-add { opacity: 1; }
.conv-add:hover { color: var(--gold, #e94560); }

.conv-group { border-top: 1px solid rgba(255,255,255,.03); }
.group-header {
  display: flex; align-items: center; gap: 6px; padding: 6px 12px;
  cursor: pointer; font-size: 12px; font-weight: 600;
}
.group-header:hover { background: rgba(255,255,255,.03); }
.expand-icon { font-size: 9px; color: var(--text2, #666); }
.group-name { flex: 1; }
.group-children { padding-left: 8px; }
</style>
