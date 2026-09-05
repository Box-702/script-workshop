<script setup>
// =====================================================================
// ProjectTree.vue —— 左侧项目树（项目 -> 对话 两级结构）
//
// 交互：
//   - 点击项目头：展开/折叠，展开时懒加载对话列表；
//   - 点击对话：切换当前对话；
//   - 双击对话标题：内联重命名（Enter/失焦提交，Esc 取消）；
//   - hover 对话出现操作按钮：重命名 / 删除；
//   - 每个项目下可「＋ 新对话」；空态给创建入口。
// 视觉：文件夹用内联 SVG（跨平台一致），对话行不带图标、纯文字缩进。
// =====================================================================

import { ref, nextTick } from 'vue'
import FolderIcon from './FolderIcon.vue'
import {
  store, toggleProject, selectConversation,
  newConversation, deleteConversation, setConversationTitle, deleteProject,
} from '../stores/app'

// ---- 内联重命名 ----
const editingId = ref(null)   // 正在编辑的对话 id
const editingPid = ref(null)  // 该对话所属的项目 id（重命名时不能用 store.pid，可能正选中别的项目）
const editText = ref('')
let renameEl = null           // 编辑输入框 DOM（函数 ref 拿到）

// ---- 内联两步确认删除（替代原生 confirm 弹窗）----
const confirmDel = ref(null) // 'proj:<id>' 或 'conv:<id>'

/** 双击标题进入编辑态（记住所属项目 id，避免在未选中的项目里改名时用错 store.pid）。 */
function startRename(pid, c) {
  editingPid.value = pid
  editingId.value = c.id
  editText.value = c.title
  nextTick(() => renameEl?.focus())
}

/** 提交重命名；空值或未变化时不请求。 */
async function commitRename() {
  const id = editingId.value
  if (!id) return
  editingId.value = null
  const pid = editingPid.value
  const conv = ((pid && store.convMap[pid]) || []).find((x) => x.id === id)
  const t = editText.value.trim()
  if (t && conv && t !== conv.title) await setConversationTitle(pid || store.pid, id, t)
}

/** 删除项目（内联确认后调用）。 */
async function doDeleteProject(p) {
  confirmDel.value = null
  await deleteProject(p.id)
}

/** 删除对话（内联确认后调用）。带上该对话所属的项目 id，刷新正确的对话列表。 */
async function doDeleteConversation(pid, c) {
  confirmDel.value = null
  await deleteConversation(c.id, pid)
}
</script>

<template>
  <aside>
    <div class="aside-head"><h2>剧本项目</h2></div>
    <div class="tree" @click="confirmDel = null">
      <!-- 空态：给创建入口，而不是死文案 -->
      <div v-if="!store.projects.length" class="tree-empty">
        <p>还没有剧本项目。</p>
        <button class="ghost small" @click="store.showNewProject = true">＋ 新建剧本</button>
      </div>

      <div v-for="p in store.projects" :key="p.id" class="proj">
        <!-- 项目头：折叠箭头 + SVG 文件夹 + 标题 + 版本数 -->
        <div
          class="proj-head"
          :class="{ active: store.pid === p.id, open: store.expanded[p.id] }"
          @click="toggleProject(p.id)"
        >
          <span class="arrow">▶</span>
          <FolderIcon :open="!!store.expanded[p.id]" class="folder" />
          <span class="t" :title="p.title">{{ p.title }}</span>
          <span class="n">{{ p.version_count }}</span>
          <span v-if="confirmDel === 'proj:' + p.id" class="confirm" @click.stop>
            <span class="confirm-txt">删除？</span>
            <button class="mini danger" @click.stop="doDeleteProject(p)">删除</button>
            <button class="mini" @click.stop="confirmDel = null">取消</button>
          </span>
          <button v-else class="del-proj" title="删除项目" @click.stop="confirmDel = 'proj:' + p.id">🗑</button>
        </div>

        <!-- 对话列表（仅展开时渲染）：无图标，纯文字与项目标题对齐 -->
        <div v-if="store.expanded[p.id]" class="conv-list">
          <div
            v-for="c in store.convMap[p.id] || []"
            :key="c.id"
            class="conv"
            :class="{ active: store.convId === c.id }"
            @click="selectConversation(p.id, c.id)"
          >
            <span class="ct" title="双击重命名" @dblclick.stop="startRename(p.id, c)">
              <input
                v-if="editingId === c.id"
                :ref="(el) => (renameEl = el)"
                v-model="editText"
                class="rename"
                @click.stop
                @dblclick.stop
                @keydown.enter.prevent="commitRename"
                @keydown.esc="editingId = null"
                @blur="commitRename"
              />
              <template v-else>{{ c.title }}</template>
            </span>
            <span v-if="confirmDel === 'conv:' + c.id" class="confirm" @click.stop>
              <span class="confirm-txt">删除？</span>
              <button class="mini danger" @click.stop="doDeleteConversation(p.id, c)">删除</button>
              <button class="mini" @click.stop="confirmDel = null">取消</button>
            </span>
            <span v-else-if="editingId !== c.id" class="ops">
              <button title="重命名" aria-label="重命名对话" @click.stop="startRename(p.id, c)">✎</button>
              <button title="删除" aria-label="删除对话" @click.stop="confirmDel = 'conv:' + c.id">🗑</button>
            </span>
          </div>
          <div class="new-conv">
            <button class="ghost small" @click="newConversation(p.id)">＋ 新对话</button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
aside {
  background: var(--panel);
  display: flex; flex-direction: column; min-height: 0;
}
.aside-head { padding: 12px 12px 8px; display: flex; align-items: center; justify-content: space-between; }
h2 { font-size: 12px; margin: 0; color: var(--muted); font-weight: 600; letter-spacing: 0.5px; }
.tree { overflow-y: auto; flex: 1; padding: 0 8px 12px; }
.proj { margin-bottom: 2px; }
.proj-head {
  display: flex; align-items: center; gap: 7px; padding: 6px 8px;
  border-radius: 8px; cursor: pointer; font-size: 13px;
  transition: background-color var(--dur) var(--ease);
}
.proj-head:hover { background: color-mix(in oklch, var(--ink) 5%, transparent); }
.proj-head.active { background: color-mix(in oklch, var(--ink) 7%, transparent); }
.del-proj {
  opacity: 0; background: transparent; border: none; color: var(--muted);
  font-size: 12px; padding: 0 3px; cursor: pointer; border-radius: 4px;
}
.proj-head:hover .del-proj { opacity: 0.7; }
.del-proj:hover { opacity: 1 !important; color: var(--bad); }

/* 内联两步确认（替代原生 confirm） */
.confirm { display: inline-flex; align-items: center; gap: 5px; flex: none; }
.confirm-txt { color: var(--bad); font-size: 11px; white-space: nowrap; }
.mini {
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  border-radius: 6px; padding: 0 7px; font-size: 11px; font-weight: 500; line-height: 1.6;
  cursor: pointer; transition: background-color var(--dur) var(--ease), color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.mini:hover { color: var(--ink); border-color: var(--line-strong); }
.mini.danger { color: var(--bad); border-color: color-mix(in oklch, var(--bad) 55%, var(--line)); }
.mini.danger:hover { background: color-mix(in oklch, var(--bad) 14%, transparent); color: var(--bad); }
.arrow { width: 11px; color: var(--dim); font-size: 9px; transition: transform var(--dur) var(--ease); flex: none; }
.proj-head.open .arrow { transform: rotate(90deg); }
.folder { width: 15px; height: 15px; flex: none; color: color-mix(in oklch, var(--ink) 58%, var(--muted)); transition: color var(--dur) var(--ease); }
.proj-head.active .folder { color: var(--ink); }
.t { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; }
.n { font-size: 10.5px; color: var(--dim); background: color-mix(in oklch, var(--ink) 6%, transparent);
  border: 1px solid color-mix(in oklch, var(--ink) 9%, transparent); border-radius: 999px; padding: 0 7px;
  line-height: 1.5; font-variant-numeric: tabular-nums; flex: none; }
.conv-list { margin: 2px 0 6px 18px; padding-left: 6px; border-left: 1px solid color-mix(in oklch, var(--ink) 9%, transparent); }
.conv {
  display: flex; align-items: center; padding: 4px 8px 4px 16px;
  border-radius: 7px; cursor: pointer; font-size: 12.5px; color: var(--muted);
  transition: background-color var(--dur) var(--ease), color var(--dur) var(--ease);
}
.conv:hover { background: color-mix(in oklch, var(--ink) 5%, transparent); color: var(--ink); }
.conv.active { background: var(--select); color: var(--ink); font-weight: 600; }
.ct { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rename { width: 100%; font-size: 12.5px; padding: 1px 5px; border-radius: 5px; }
.ops { display: none; gap: 2px; }
.conv:hover .ops { display: flex; }
.ops button {
  background: transparent; border: none; color: inherit; cursor: pointer;
  font-size: 12px; padding: 0 3px; opacity: 0.7; border-radius: 4px;
}
.ops button:hover { opacity: 1; background: color-mix(in oklch, var(--ink) 10%, transparent); }
.new-conv { margin: 2px 0 6px 8px; }
.tree-empty { color: var(--dim); font-size: 12px; padding: 10px 8px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.tree-empty p { margin: 0; }
</style>
