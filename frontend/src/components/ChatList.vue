<template>
  <div class="chat-list">
    <div class="chat-header">
      <span class="chat-title">对话</span>
      <button class="btn-new" @click="onNew" title="新建聊天" aria-label="新建聊天">＋</button>
    </div>

    <!-- 未归类对话（还没落到任何项目下；在对话里创建项目后会自动归档） -->
    <div class="conv-section">
      <div v-if="globalConvs.length" class="section-label">未归类</div>
      <div
        v-for="conv in globalConvs"
        :key="conv.id"
        :class="['conv-item', { active: isActive(null, conv.id) }]"
        @click="onSelect(null, conv.id)"
      >
        <span class="conv-dot" aria-hidden="true"></span>
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
        <p class="conv-empty-title">从一句话开始你的第一个故事</p>
        <button class="conv-empty-cta" @click="onNew">新建对话</button>
        <div class="conv-empty-tips" role="list" aria-label="示例">
          <button v-for="t in EMPTY_TIPS" :key="t" class="conv-empty-tip" role="listitem" @click="useTip(t)">{{ t }}</button>
        </div>
      </div>
    </div>

    <!-- 项目（点组头打开该项目最近的对话；箭头折叠/展开） -->
    <div v-for="p in projects" :key="p.id" class="conv-group">
      <div class="group-header" @click="openProject(p.id)">
        <span class="expand-icon" :class="{ open: expanded[p.id] }" @click.stop="toggleExpand(p.id)">▶</span>
        <span class="group-name">{{ p.title }}</span>
      </div>
      <div v-if="expanded[p.id]" class="group-children">
        <div
          v-for="conv in (convMap[p.id] || [])"
          :key="conv.id"
          :class="['conv-item', { active: isActive(p.id, conv.id) }]"
          @click="onSelect(p.id, conv.id)"
        >
          <span class="conv-dot" aria-hidden="true"></span>
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
        <button class="conv-add" @click="onNewProject(p.id)">
          <span aria-hidden="true">＋</span> 新对话
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { store, newGlobalConversation, selectGlobalConversation, loadGlobalConversations, newConversation, selectConversation, selectProject, setConversationTitle, deleteConversation, loadConversations, toggleProject } from '../stores/app.js'

const globalConvs = computed(() => store.globalConvs)
const projects = computed(() => store.projects)
const convMap = computed(() => store.convMap)
const expanded = computed(() => store.expanded)

const editingId = ref(null)
const editTitle = ref('')
const editInput = ref(null)

// 空态示例模板：新建对话后把示例填进输入框（不自动发送）。
const EMPTY_TIPS = [
  '一个失去记忆的出租车司机，在雨夜接到未来的自己。',
  '把我贴进项目里的原文改编成 3 分钟短剧。',
  '从人物开始：一个想退休却总被叫回去的深夜出诊兽医。',
]

function useTip(t) {
  onNew()
  store.draft = t
  store.draftSeq++
}

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

/** 打开项目：展开并进入该项目最近的对话（组头点击）。 */
function openProject(pid) {
  if (store.pid === pid && store.convId) {
    // 已在该项目内：只保证展开，不打断当前对话。
    if (!expanded.value[pid]) toggleExpand(pid)
    return
  }
  selectProject(pid)
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
.chat-list { display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
.chat-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 12px 10px; border-bottom: 1px solid var(--line);
}
.chat-title { font-size: 13.5px; font-weight: 650; color: var(--ink); }
.btn-new {
  position: relative;
  width: 36px; height: 36px; border-radius: 8px;
  border: 1px solid var(--line); background: transparent;
  color: var(--muted); cursor: pointer; font-size: 13px; line-height: 1;
  display: flex; align-items: center; justify-content: center; padding: 0;
  transition: color 150ms var(--ease), border-color 150ms var(--ease), background 150ms var(--ease);
}
.btn-new::after { content: ''; position: absolute; inset: -4px; border-radius: inherit; }
.btn-new:hover {
  border-color: color-mix(in oklch, var(--gold) 45%, var(--line));
  color: var(--gold); background: var(--gold-soft);
}

.conv-section { overflow: visible; padding: 6px 0; }

.section-label {
  padding: 8px 14px 2px;
  font-size: 9.5px; font-weight: 650; color: var(--dim);
  text-transform: uppercase; letter-spacing: .14em;
}

.conv-item {
  position: relative;
  display: flex; align-items: center; gap: 8px; padding: 12px 10px 12px 14px;
  margin: 1px 6px; border-radius: 8px;
  cursor: pointer; font-size: 12.5px; color: var(--muted);
  transition: background .14s var(--ease), color .14s var(--ease);
}
.conv-item:hover { background: color-mix(in oklch, var(--ink) 5%, transparent); color: var(--ink); }
.conv-item.active {
  background: color-mix(in oklch, var(--gold) 9%, transparent); color: var(--ink);
}
.conv-item.active::before {
  content: ''; position: absolute; left: 0; top: 7px; bottom: 7px; width: 2px;
  border-radius: 2px; background: var(--gold);
}
.conv-dot {
  flex: none; width: 5px; height: 5px; border-radius: 50%;
  background: transparent; border: 1px solid var(--dim);
  transition: background .14s, border-color .14s;
}
.conv-item.active .conv-dot { background: var(--gold); border-color: var(--gold); }
.conv-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-count {
  flex: none; font-size: 10px; color: var(--dim);
  font-variant-numeric: tabular-nums;
}
.conv-actions { display: flex; gap: 2px; opacity: 0; pointer-events: none; transition: opacity 140ms var(--ease); }
.conv-item:hover .conv-actions, .conv-item:focus-within .conv-actions { opacity: 1; pointer-events: auto; }
.btn-tiny {
  position: relative;
  background: transparent; border: none; border-radius: 4px;
  cursor: pointer; font-size: 12px; padding: 5px 6px;
  opacity: .55; color: var(--muted);
  transition: opacity 120ms, background 120ms;
}
.btn-tiny::after { content: ''; position: absolute; inset: -6px; }
.btn-tiny:hover { opacity: 1; background: color-mix(in oklch, var(--ink) 8%, transparent); }
.conv-edit {
  flex: 1; min-width: 0; background: var(--code-bg, #111);
  border: 1px solid color-mix(in oklch, var(--gold) 45%, var(--line));
  border-radius: 5px; color: var(--text, #eee); font-size: 12px; padding: 3px 6px; outline: none;
}
.conv-empty {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 26px 14px; text-align: center;
}
.conv-empty-title { margin: 0; font-size: 13.5px; font-weight: 650; color: var(--ink); line-height: 1.6; }
.conv-empty-cta { min-height: 44px; padding: 0 20px; border-radius: 10px; font-size: 13px; font-weight: 650; }
.conv-empty-tips { display: flex; flex-direction: column; gap: 6px; width: 100%; margin-top: 4px; }
.conv-empty-tip {
  min-height: 44px; padding: 8px 12px;
  background: transparent; border: 1px solid var(--line); border-radius: 10px;
  color: var(--muted); font-size: 12px; font-weight: 400; text-align: left;
  transition: color 150ms var(--ease), border-color 150ms var(--ease), background 150ms var(--ease);
}
.conv-empty-tip:hover { color: var(--ink); border-color: color-mix(in oklch, var(--gold) 40%, var(--line)); background: color-mix(in oklch, var(--gold) 6%, transparent); }

/* 「＋ 新对话」：常显的安静虚线胶囊（不再是 hover 才冒出来的裸文字） */
.conv-add {
  display: flex; align-items: center; gap: 5px;
  width: calc(100% - 20px); margin: 2px 10px 6px; padding: 10px 9px;
  border: 1px dashed var(--line); border-radius: 7px;
  background: transparent; color: var(--dim);
  cursor: pointer; font-size: 12.5px; font-weight: 500; text-align: left;
  transition: color 150ms var(--ease), border-color 150ms var(--ease), background 150ms var(--ease);
}
.conv-add:hover {
  color: var(--gold);
  border-color: color-mix(in oklch, var(--gold) 40%, var(--line));
  background: var(--gold-soft);
}

.conv-group { border-top: 1px solid color-mix(in oklch, var(--line) 55%, transparent); }
.group-header {
  display: flex; align-items: center; gap: 6px; padding: 8px 10px 5px;
  cursor: pointer; font-size: 11px; font-weight: 650; color: var(--dim);
  letter-spacing: .02em;
}
.group-header:hover { color: var(--muted); }
.expand-icon { font-size: 8px; color: var(--dim); padding: 4px 2px; transition: transform 200ms var(--ease); }
.expand-icon.open { transform: rotate(90deg); }
.group-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-children { padding-bottom: 2px; }
</style>
