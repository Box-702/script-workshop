<script setup>
// =====================================================================
// ProjectTree.vue —— 左侧导航（轻量文字列表风格）
//
// 借鉴 Linear/Cursor 的侧栏：干净的文字列表，无按钮装饰，
// hover 微亮，选中态极简（左侧色条 + 背景微变）。
// =====================================================================

import { ref, computed, nextTick } from 'vue'
import {
  store, toggleProject, selectConversation, focusScene,
  newConversation, deleteConversation, setConversationTitle, deleteProject,
} from '../stores/app'

// ---- 搜索 ----
const search = ref('')
const filteredProjects = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return store.projects
  return store.projects.filter((p) => p.title.toLowerCase().includes(q))
})

// ---- 内联重命名 ----
const editingId = ref(null)
const editingPid = ref(null)
const editText = ref('')
let renameEl = null

// ---- 确认删除 ----
const confirmDel = ref(null)

// ---- 场景拖拽排序 ----
const dragScene = ref(null)   // { projectId, sceneId }
const dragOverScene = ref(null) // { projectId, sceneId }

function onSceneDragStart(e, pid, sc) {
  dragScene.value = { projectId: pid, sceneId: sc.id }
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', sc.id)
}
function onSceneDragOver(e, pid, sc) {
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
  dragOverScene.value = { projectId: pid, sceneId: sc.id }
}
function onSceneDragLeave() {
  dragOverScene.value = null
}
function onSceneDrop(e, pid, sc) {
  e.preventDefault()
  if (!dragScene.value || dragScene.value.projectId !== pid) { dragScene.value = null; return }
  const fromId = dragScene.value.sceneId
  const toId = sc.id
  if (fromId === toId) { dragScene.value = null; return }
  const scenes = store.scenesMap[pid] || []
  const fromIdx = scenes.findIndex((s) => s.id === fromId)
  const toIdx = scenes.findIndex((s) => s.id === toId)
  if (fromIdx < 0 || toIdx < 0) { dragScene.value = null; return }
  const reordered = [...scenes]
  const [moved] = reordered.splice(fromIdx, 1)
  reordered.splice(toIdx, 0, moved)
  store.scenesMap[pid] = reordered
  dragScene.value = null
  dragOverScene.value = null
}
function onSceneDragEnd() {
  dragScene.value = null
  dragOverScene.value = null
}

function startRename(pid, c) {
  editingPid.value = pid
  editingId.value = c.id
  editText.value = c.title
  nextTick(() => renameEl?.focus())
}
async function commitRename() {
  const id = editingId.value
  if (!id) return
  editingId.value = null
  const pid = editingPid.value
  const conv = ((pid && store.convMap[pid]) || []).find((x) => x.id === id)
  const t = editText.value.trim()
  if (t && conv && t !== conv.title) await setConversationTitle(pid || store.pid, id, t)
}
async function doDeleteProject(p) {
  confirmDel.value = null
  await deleteProject(p.id)
}
async function doDeleteConversation(pid, c) {
  confirmDel.value = null
  await deleteConversation(c.id, pid)
}
</script>

<template>
  <aside>
    <!-- 标题 -->
    <div class="aside-head">
      <h2>剧本工坊</h2>
      <span class="version">v0.4</span>
    </div>

    <!-- 新建按钮：极简 -->
    <button class="new-btn" @click="store.showNewProject = true">＋ 新建剧本</button>

    <!-- 搜索 -->
    <input v-model="search" class="search" placeholder="搜索…" spellcheck="false" />

    <!-- 项目列表 -->
    <div class="list" @click="confirmDel = null">
      <div v-if="!filteredProjects.length && !search" class="empty">
        <p>还没有剧本</p>
        <p class="empty-sub">创建一个开始写作</p>
      </div>
      <div v-if="!filteredProjects.length && search" class="empty">
        <p>没有匹配的项目</p>
      </div>

      <div v-for="p in filteredProjects" :key="p.id" class="proj">
        <!-- 项目行 -->
        <div
          class="item"
          :class="{ active: store.pid === p.id }"
          @click="toggleProject(p.id)"
        >
          <span class="arrow" :class="{ open: store.expanded[p.id] }">›</span>
          <span class="name">{{ p.title }}</span>
          <span v-if="confirmDel === 'proj:' + p.id" class="confirm" @click.stop>
            <button class="confirm-del" @click.stop="doDeleteProject(p)">删除</button>
            <button class="confirm-cancel" @click.stop="confirmDel = null">取消</button>
          </span>
          <button v-else class="del" @click.stop="confirmDel = 'proj:' + p.id">…</button>
        </div>

        <!-- 展开内容 -->
        <div v-if="store.expanded[p.id]" class="children">
          <!-- 场景 -->
          <div v-if="(store.scenesMap[p.id] || []).length" class="group">
            <div class="group-label">场景</div>
            <div
              v-for="sc in store.scenesMap[p.id]" :key="sc.id"
              class="item scene"
              :class="{
                active: store.focusedSceneId === sc.id,
                'drag-over': dragOverScene?.sceneId === sc.id && dragOverScene?.projectId === p.id
              }"
              draggable="true"
              @click="focusScene(sc.id)"
              @dragstart="onSceneDragStart($event, p.id, sc)"
              @dragover="onSceneDragOver($event, p.id, sc)"
              @dragleave="onSceneDragLeave"
              @drop="onSceneDrop($event, p.id, sc)"
              @dragend="onSceneDragEnd"
            >
              <span class="drag-handle" aria-hidden="true">⠿</span>
              <span class="name">{{ sc.title }}</span>
              <span class="meta">{{ (sc.characters || []).length }}人 · {{ sc.beats_count }}拍</span>
            </div>
          </div>

          <!-- 对话 -->
          <div class="group">
            <div class="group-label">对话</div>
            <div
              v-for="c in store.convMap[p.id] || []"
              :key="c.id"
              class="item"
              :class="{ active: store.convId === c.id }"
              @click="selectConversation(p.id, c.id)"
            >
              <span v-if="editingId === c.id" class="name">
                <input
                  :ref="(el) => (renameEl = el)"
                  v-model="editText"
                  class="rename-input"
                  @click.stop
                  @keydown.enter.prevent="commitRename"
                  @keydown.esc="editingId = null"
                  @blur="commitRename"
                />
              </span>
              <span v-else class="name" @dblclick.stop="startRename(p.id, c)">{{ c.title }}</span>
              <span v-if="editingId !== c.id" class="ops">
                <button @click.stop="startRename(p.id, c)">✎</button>
                <button v-if="confirmDel !== 'conv:' + c.id" @click.stop="confirmDel = 'conv:' + c.id">🗑</button>
                <template v-if="confirmDel === 'conv:' + c.id">
                  <button class="confirm-del" @click.stop="doDeleteConversation(p.id, c)">删</button>
                  <button class="confirm-cancel" @click.stop="confirmDel = null">消</button>
                </template>
              </span>
            </div>
            <button class="item add-conv" @click="newConversation(p.id)">＋ 新对话</button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
aside {
  background: color-mix(in oklch, var(--panel) 60%, var(--bg));
  display: flex; flex-direction: column; min-height: 0;
  border-right: 1px solid var(--line);
}

/* 标题区 */
.aside-head { padding: 16px 16px 4px; display: flex; align-items: baseline; gap: 6px; }
h2 { font-size: 13px; margin: 0; font-weight: 700; color: var(--ink); letter-spacing: 0.01em; }
.version { font-size: 10px; color: var(--dim); font-family: var(--mono); }

/* 新建按钮 */
.new-btn {
  margin: 8px 12px 0; padding: 6px 10px;
  background: transparent; border: 1px dashed var(--line);
  border-radius: 8px; color: var(--muted); font-size: 12px;
  text-align: left; cursor: pointer;
  transition: all 200ms var(--ease);
}
.new-btn:hover { color: var(--ink); border-color: var(--gold); background: color-mix(in oklch, var(--gold) 5%, transparent); }

/* 搜索框 */
.search {
  margin: 10px 12px 6px; padding: 5px 10px;
  background: transparent; border: 1px solid var(--line); border-radius: 6px;
  font-size: 11.5px; color: var(--ink); outline: none;
  transition: border-color 200ms var(--ease), box-shadow 200ms var(--ease);
}
.search::placeholder { color: var(--dim); }
.search:focus { border-color: color-mix(in oklch, var(--gold) 40%, var(--line)); box-shadow: 0 0 0 2px color-mix(in oklch, var(--gold) 8%, transparent); }

/* 列表 */
.list { flex: 1; overflow-y: auto; padding: 4px 8px 16px; }
.empty { color: var(--dim); font-size: 12px; padding: 20px 8px; }
.empty p { margin: 2px 0; }
.empty-sub { font-size: 11px; }

/* 项目行：滑入动画 */
.item {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; border-radius: 6px; cursor: pointer;
  font-size: 12.5px; color: var(--muted);
  transition: all 200ms var(--ease);
  position: relative;
  animation: slide-in-left 250ms var(--ease) both;
}
.item:hover { color: var(--ink); background: color-mix(in oklch, var(--ink) 4%, transparent); }
.item.active {
  color: var(--ink); font-weight: 500;
  background: color-mix(in oklch, var(--gold) 6%, transparent);
}
.item.active::before {
  content: ''; position: absolute; left: 0; top: 6px; bottom: 6px;
  width: 2px; border-radius: 1px; background: var(--gold);
  animation: grow-in 300ms var(--ease-bounce) both;
}

/* 子行交错延迟 */
.children .item:nth-child(1) { animation-delay: 0ms; }
.children .item:nth-child(2) { animation-delay: 30ms; }
.children .item:nth-child(3) { animation-delay: 60ms; }
.children .item:nth-child(4) { animation-delay: 90ms; }
.children .item:nth-child(5) { animation-delay: 120ms; }

@keyframes slide-in-left {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}
@keyframes grow-in {
  from { transform: scaleY(0); }
  to { transform: scaleY(1); }
}

/* 展开/折叠动画 */
.children {
  overflow: hidden;
  animation: expand-in 300ms var(--ease) both;
}
@keyframes expand-in {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 500px; }
}

/* 箭头 */
.arrow { font-size: 10px; color: var(--dim); transition: transform 250ms var(--ease-bounce); flex: none; width: 10px; text-align: center; }
.arrow.open { transform: rotate(90deg); }

/* 名称 */
.name { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 元数据 */
.meta { font-size: 10px; color: var(--dim); flex: none; font-variant-numeric: tabular-nums; }

/* 删除按钮 */
.del {
  opacity: 0; background: transparent; border: none; color: var(--dim);
  font-size: 11px; padding: 0 4px; cursor: pointer; flex: none;
  transition: all 200ms var(--ease);
}
.item:hover .del { opacity: 0.5; }
.del:hover { color: var(--bad) !important; opacity: 1 !important; }

/* 分组标签 */
.group { margin-bottom: 4px; }
.group-label {
  font-size: 10px; color: var(--dim); font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.3px;
  padding: 6px 8px 2px;
  animation: slide-in-left 200ms var(--ease) both;
}

/* 场景行 */
.scene { padding: 4px 8px; cursor: grab; }
.scene:active { cursor: grabbing; }
.scene .name { font-size: 12px; }
.drag-handle { font-size: 10px; color: var(--dim); opacity: 0; transition: opacity 200ms var(--ease); flex: none; }
.scene:hover .drag-handle { opacity: 0.5; }
.scene.drag-over { border-top: 2px solid var(--gold); padding-top: 2px; }

/* 对话行操作 */
.ops { display: none; gap: 2px; flex: none; }
.item:hover > .ops { display: flex; }
.ops button {
  background: transparent; border: none; color: var(--dim); cursor: pointer;
  font-size: 10px; padding: 0 3px; border-radius: 3px;
  transition: color 200ms var(--ease);
}
.ops button:hover { color: var(--ink); }

/* 内联确认 */
.confirm { display: inline-flex; gap: 3px; flex: none; animation: pop-in 200ms var(--ease-bounce) both; }
.confirm-del { color: var(--bad) !important; font-size: 10px !important; }
.confirm-cancel { font-size: 10px !important; }

/* 重命名输入 */
.rename-input {
  width: 100%; font-size: 12.5px; padding: 1px 4px; border-radius: 4px;
  border: 1px solid var(--line); background: var(--bg); color: var(--ink);
}

/* 新建对话 */
.add-conv {
  font-size: 11.5px; color: var(--dim); padding: 4px 8px;
  opacity: 0; transition: opacity 200ms var(--ease);
}
.group:hover .add-conv { opacity: 1; }
.add-conv:hover { color: var(--muted); }
</style>
