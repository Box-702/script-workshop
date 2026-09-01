<script setup>
// =====================================================================
// WorkspaceModal.vue —— 工作目录设置弹窗（三选一落盘模式）
//
// 三种模式：
//   1. 默认落盘：写到 <项目根>/data/workspace
//   2. 落盘到指定文件夹：用 Windows 原生选择框或手输路径
//   3. 仅应用内、不落盘：不写磁盘文件（数据库照常存储）
// 选了只影响「是否/往哪写真实文件」，不影响应用功能。
// =====================================================================

import { ref, watch, nextTick, onUnmounted } from 'vue'
import FolderIcon from './FolderIcon.vue'
import FolderTree from './FolderTree.vue'
import { store, setWorkspace, selectWorkspaceDirectory } from '../stores/app'

const MODES = [
  { key: 'default', label: '默认落盘', desc: '写到项目下的 data/workspace' },
  { key: 'custom', label: '指定文件夹', desc: '用原生选择框选你想要的目录' },
  { key: 'in_app', label: '仅应用内', desc: '不写磁盘文件，数据库照常存储' },
]

const mode = ref('default')
const customRoot = ref('')
const err = ref('')
const saving = ref(false)
const picking = ref(false)
const pathInput = ref(null)

function onKey(e) {
  if (e.key === 'Escape' && store.showWorkspace && !saving.value && !picking.value) store.showWorkspace = false
}

watch(() => store.showWorkspace, (open) => {
  if (open) {
    const m = store.workspace?.mode || 'default'
    mode.value = m === 'in_app' ? 'in_app' : (m === 'custom' ? 'custom' : 'default')
    customRoot.value = store.workspace?.root || ''
    err.value = ''
    nextTick(() => { if (mode.value === 'custom') pathInput.value?.focus() })
    window.addEventListener('keydown', onKey)
  } else {
    window.removeEventListener('keydown', onKey)
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey))

function baseRoot() { return store.workspace?.root || '' }

async function apply() {
  if (saving.value) return
  err.value = ''
  let root = ''
  let persist = true
  if (mode.value === 'in_app') { persist = false; root = '' }
  else if (mode.value === 'custom') {
    root = customRoot.value.trim()
    if (!root) { err.value = '请选择或填写文件夹路径'; return }
    persist = true
  } else { root = baseRoot(); persist = true }
  saving.value = true
  try {
    await setWorkspace(root, persist)
    store.showWorkspace = false
  } catch (e) { err.value = '设置失败：' + e.message } finally { saving.value = false }
}

async function browse() {
  if (picking.value) return
  err.value = ''
  picking.value = true
  mode.value = 'custom'
  try {
    const picked = await selectWorkspaceDirectory()
    if (picked) {
      customRoot.value = picked
      store.showWorkspace = false
    }
  } catch (e) {
    err.value = '无法弹出选择框：' + e.message + '（可手动输入路径）'
  } finally {
    picking.value = false
  }
}
</script>

<template>
  <div v-if="store.showWorkspace" class="modal-backdrop" @click.self="!saving && !picking && (store.showWorkspace = false)">
    <div class="modal" role="dialog" aria-label="工作目录">
      <!-- 头部 -->
      <div class="head">
        <span class="head-ic"><FolderIcon :open="true" /></span>
        <div>
          <h3>工作目录</h3>
          <div class="sub">把剧本产物落到你电脑上的真实文件夹；也可以只在应用内不改动磁盘</div>
        </div>
      </div>

      <!-- 模式选择 -->
      <label class="lbl">落盘模式</label>
      <div class="modes">
        <label v-for="m in MODES" :key="m.key" class="mode" :class="{ active: mode === m.key }">
          <input type="radio" :value="m.key" v-model="mode" />
          <span class="m-label">{{ m.label }}</span>
          <span class="m-desc">{{ m.desc }}</span>
        </label>
      </div>

      <!-- 指定文件夹：路径行 -->
      <template v-if="mode === 'custom'">
        <label class="lbl">目录路径</label>
        <div class="path-row">
          <input ref="pathInput" v-model="customRoot" placeholder="例如：C:\Users\你\Documents\我的剧本" @input="err = ''" @keydown.enter="apply" />
          <button class="ghost" :disabled="picking" @click="browse">
            <svg viewBox="0 0 16 16" class="ic-folder" aria-hidden="true"><path d="M2.5 4.5c0-.55.45-1 1-1h1.6c.27 0 .52.11.71.29l.44.44c.19.19.44.29.71.29h3.05c.55 0 1 .45 1 1v6.98c0 .55-.45 1-1 1H3.5c-.55 0-1-.45-1-1V4.5z" fill="currentColor"/></svg>
            {{ picking ? '选择中…' : '选择文件夹' }}
          </button>
        </div>
        <div v-if="baseRoot() && mode === 'custom'" class="current" :title="baseRoot()">
          <span class="dot"></span>当前默认：<code class="mono">{{ baseRoot() }}</code>
        </div>
      </template>

      <!-- 默认模式：展示当前根 -->
      <div v-else-if="mode === 'default' && baseRoot()" class="current" :title="baseRoot()">
        <span class="dot"></span>将写入：<code class="mono">{{ baseRoot() }}</code>
      </div>
      <div v-else-if="mode === 'in_app'" class="hint">仅应用内模式：不修改磁盘，只存在应用里（数据库照常存储）。</div>

      <!-- 自动分格 -->
      <div class="struct">
        <div class="struct-title">
          <FolderIcon :open="true" />
          <span>自动分格</span>
          <span class="struct-sub">每个剧本一个文件夹</span>
        </div>
        <FolderTree :root="mode === 'in_app' ? '（仅应用内）' : (mode === 'custom' ? (customRoot || '（待设置）') : (baseRoot() || '（待设置）'))" />
      </div>

      <div v-if="err" class="err">⚠️ {{ err }}</div>

      <div class="foot">
        <button class="ghost" :disabled="saving" @click="store.showWorkspace = false">取消</button>
        <button :disabled="saving" @click="apply">{{ saving ? '设置中…' : '应用' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: oklch(0 0 0 / 0.55);
  display: flex; align-items: center; justify-content: center; z-index: 60;
  animation: fade-in 180ms var(--ease);
}
.modal {
  background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
  width: 580px; max-width: 94vw; max-height: 88vh; overflow-y: auto;
  padding: 20px 22px; box-shadow: 0 24px 64px oklch(0 0 0 / 0.52);
  animation: pop-in 180ms var(--ease);
}
.head { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 4px; }
.head-ic { width: 40px; height: 40px; border-radius: 11px; display: inline-grid; place-items: center;
  background: color-mix(in oklch, var(--ink) 7%, transparent); color: var(--ink); flex: none; }
.head-ic .folder-icon { width: 22px; height: 22px; }
h3 { margin: 0; font-size: 16px; font-weight: 700; }
.sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
.lbl { display: block; font-size: 12px; color: var(--muted); margin: 16px 0 6px; font-weight: 600; }

/* 三选一模式 */
.modes { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.mode { display: flex; flex-direction: column; gap: 2px; padding: 10px 12px; border: 1px solid var(--line);
  border-radius: 11px; cursor: pointer; transition: border-color var(--dur) var(--ease), background-color var(--dur) var(--ease); }
.mode:hover { border-color: var(--line-strong); background: color-mix(in oklch, var(--ink) 3%, transparent); }
.mode.active { border-color: color-mix(in oklch, var(--ink) 40%, var(--line)); background: color-mix(in oklch, var(--ink) 6%, transparent); }
.mode input { position: absolute; opacity: 0; pointer-events: none; }
.m-label { font-size: 12.5px; font-weight: 600; color: var(--ink); }
.m-desc { font-size: 11px; color: var(--muted); line-height: 1.4; }

.path-row { display: flex; gap: 8px; }
.path-row input { flex: 1; min-width: 0; }
.path-row button { flex: none; display: inline-flex; align-items: center; gap: 6px; }
.ic-folder { width: 14px; height: 14px; }
.current { display: flex; align-items: center; gap: 6px; color: var(--ok); font-size: 12px; margin-top: 8px; }
.current .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); flex: none; }
.current code { color: inherit; }
.hint { color: var(--dim); font-size: 11.5px; margin-top: 8px; }

.struct { margin-top: 18px; background: var(--code-bg); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; }
.struct-title { display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--muted); font-weight: 600; margin-bottom: 8px; }
.struct-title .folder-icon { width: 14px; height: 14px; color: var(--muted); }
.struct-sub { color: var(--dim); font-weight: 400; margin-left: auto; font-size: 11.5px; }

.foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.err { color: var(--bad); font-size: 12px; margin-top: 10px; }
@keyframes fade-in { from { opacity: 0; } }
@keyframes pop-in { from { opacity: 0; transform: scale(0.96) translateY(6px); } }
</style>
