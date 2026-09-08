<template>
  <div class="workspace-tree">
    <div class="ws-header">
      <span class="ws-title">📂 工作区</span>
      <button class="btn-tiny" @click="onRefresh" title="刷新">🔄</button>
    </div>

    <div v-if="!tree" class="ws-empty">
      <p>未配置工作目录</p>
      <button class="btn-small" @click="$emit('open-workspace')">设置工作目录</button>
    </div>

    <div v-else class="ws-content">
      <div class="ws-root">{{ tree.root }}</div>
      <div v-for="folder in tree.folders" :key="folder.name" class="ws-folder">
        <div class="folder-header" @click="toggle(folder.name)">
          <span class="expand-icon">{{ isOpen(folder.name) ? '▼' : '▶' }}</span>
          <span class="folder-icon">📁</span>
          <span class="folder-name">{{ folder.name }}</span>
        </div>
        <div v-if="isOpen(folder.name)" class="folder-children">
          <div
            v-for="sub in (folder.folders || [])"
            :key="sub.name"
            class="folder-item"
          >
            <span class="item-icon">{{ sub.type === 'dir' ? '📁' : '📄' }}</span>
            <span class="item-name">{{ sub.name }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { store, loadWorkspaceTree } from '../stores/app.js'

const tree = computed(() => store.workspaceTree)
const openFolders = reactive(new Set())

function isOpen(name) { return openFolders.has(name) }
function toggle(name) {
  if (openFolders.has(name)) openFolders.delete(name)
  else openFolders.add(name)
}

function onRefresh() {
  loadWorkspaceTree()
}
</script>

<style scoped>
.workspace-tree { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.ws-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; border-bottom: 1px solid var(--border, #222);
}
.ws-title { font-size: 13px; font-weight: 600; }
.btn-tiny {
  background: none; border: none; cursor: pointer; font-size: 12px; padding: 2px;
  opacity: .6;
}
.btn-tiny:hover { opacity: 1; }

.ws-empty { padding: 20px 12px; text-align: center; color: var(--text2, #666); font-size: 12px; }
.btn-small {
  margin-top: 8px; padding: 5px 12px; border: 1px solid var(--border, #333);
  border-radius: 5px; background: none; color: var(--text, #eee); cursor: pointer; font-size: 11px;
}
.btn-small:hover { border-color: var(--gold, #e94560); }

.ws-content { flex: 1; overflow-y: auto; padding: 4px 0; }
.ws-root { padding: 4px 12px; font-size: 10px; color: var(--text2, #555); word-break: break-all; }

.ws-folder { }
.folder-header {
  display: flex; align-items: center; gap: 5px; padding: 5px 12px;
  cursor: pointer; font-size: 12px;
}
.folder-header:hover { background: rgba(255,255,255,.03); }
.expand-icon { font-size: 9px; color: var(--text2, #666); }
.folder-icon { font-size: 12px; }
.folder-name { flex: 1; }
.folder-children { padding-left: 12px; }
.folder-item {
  display: flex; align-items: center; gap: 5px; padding: 3px 12px;
  font-size: 11px; color: var(--text2, #888);
}
.item-icon { font-size: 10px; }
</style>
