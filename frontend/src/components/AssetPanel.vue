<template>
  <div class="asset-panel">
    <div class="asset-head">
      <select class="proj-select" :value="store.pid || ''" @change="onPickProject($event.target.value)">
        <option value="" disabled>选择项目…</option>
        <option v-for="p in store.projects" :key="p.id" :value="p.id">{{ p.title }}</option>
      </select>
      <button class="upload-btn" :disabled="!store.pid || uploading" @click="fileInput?.click()">
        {{ uploading ? '上传中…' : '↑ 上传视频' }}
      </button>
      <input
        ref="fileInput"
        type="file"
        accept=".mp4,.mov,.webm,.m4v,.mkv,.avi"
        hidden
        @change="onFilePicked"
      />
    </div>

    <!-- URL 粘贴入口 -->
    <div class="url-row">
      <input
        v-model.trim="urlInput"
        class="url-input"
        type="url"
        placeholder="粘贴公网视频直链（https://…mp4）"
        spellcheck="false"
        @keydown.enter.prevent="addUrl"
      />
      <button class="url-add" :disabled="!store.pid || !urlInput" @click="addUrl">添加</button>
    </div>

    <p class="hint">
      上传的文件可预览、归档（服务商拉取需公网 URL）；登记的公网直链可直接作参考视频喂给 MiniMax。
      在镜头「编辑 Prompt」里粘贴素材链接即可挂为参考视频。
    </p>

    <div class="asset-list">
      <div v-if="!store.pid" class="empty">先在「项目」里选择一个项目</div>
      <div v-else-if="loading" class="empty">加载中…</div>
      <div v-else-if="!assets.length" class="empty">还没有素材</div>
      <div v-for="a in assets" v-else :key="a.id" class="asset-row">
        <button class="play" :title="'预览 ' + a.name" @click="preview(a)">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 2l7 4-7 4z" fill="currentColor" /></svg>
        </button>
        <div class="info" @click="preview(a)">
          <span class="name" :title="a.name">{{ a.name }}</span>
          <span class="sub">
            <span :class="['src', a.source]">{{ a.source === 'upload' ? '上传' : '链接' }}</span>
            {{ formatTime(a.created_at) }}
          </span>
        </div>
        <button class="op" title="复制链接" @click="copyUrl(a)">⧉</button>
        <button class="op danger" title="删除" @click="remove(a)">×</button>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="previewUrl" class="preview-mask" @click.self="previewUrl = ''">
        <div class="preview-box">
          <div class="preview-head">
            <span>{{ previewName }}</span>
            <button class="close" @click="previewUrl = ''">×</button>
          </div>
          <video :src="previewUrl" controls autoplay class="preview-video" />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { store, notify } from '../stores/app'
import { uploadAsset, addAssetUrl, listAssets, deleteAsset } from '../api'

const assets = ref([])
const loading = ref(false)
const uploading = ref(false)
const urlInput = ref('')
const fileInput = ref(null)
const previewUrl = ref('')
const previewName = ref('')

async function refresh() {
  if (!store.pid) { assets.value = []; return }
  loading.value = true
  try {
    assets.value = await listAssets(store.pid, 'video')
  } catch (e) {
    notify('素材列表加载失败：' + e.message, 'error')
  } finally {
    loading.value = false
  }
}

async function onFilePicked(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file || !store.pid) return
  uploading.value = true
  try {
    await uploadAsset(store.pid, file)
    notify(`已上传：${file.name}`, 'ok')
    await refresh()
  } catch (err) {
    notify('上传失败：' + err.message, 'error')
  } finally {
    uploading.value = false
  }
}

async function addUrl() {
  if (!urlInput.value || !store.pid) return
  try {
    await addAssetUrl(store.pid, urlInput.value)
    urlInput.value = ''
    notify('素材链接已登记', 'ok')
    await refresh()
  } catch (e) {
    notify('登记失败：' + e.message, 'error')
  }
}

async function remove(a) {
  try {
    await deleteAsset(a.id)
    await refresh()
  } catch (e) {
    notify('删除失败：' + e.message, 'error')
  }
}

async function copyUrl(a) {
  const abs = a.url.startsWith('http') ? a.url : location.origin + a.url
  try {
    await navigator.clipboard.writeText(abs)
    notify('链接已复制', 'ok')
  } catch { /* 剪贴板不可用时静默 */ }
}

function preview(a) {
  previewName.value = a.name
  previewUrl.value = a.url
}

function onPickProject(pid) {
  if (pid && pid !== store.pid) store.pid = pid
}

function formatTime(v) {
  if (!v) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(v))
}

onMounted(refresh)
watch(() => store.pid, refresh)
</script>

<style scoped>
.asset-panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.asset-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 12px 10px; border-bottom: 1px solid var(--line);
}
.asset-title { font-size: 13.5px; font-weight: 650; color: var(--ink); }
.proj-select {
  flex: 1; min-width: 0; padding: 5px 8px;
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 7px;
  color: var(--ink); font-size: 11.5px; outline: none; cursor: pointer;
}
.proj-select:focus { border-color: color-mix(in oklch, var(--gold) 40%, var(--line)); }
.upload-btn { flex: none; }
.upload-btn {
  padding: 4px 10px; border: 1px solid var(--line); border-radius: 7px;
  background: transparent; color: var(--muted); font-size: 11px; cursor: pointer;
  transition: color 150ms var(--ease), border-color 150ms var(--ease), background 150ms var(--ease);
}
.upload-btn:hover:not(:disabled) {
  color: var(--gold);
  border-color: color-mix(in oklch, var(--gold) 45%, var(--line));
  background: var(--gold-soft);
}
.upload-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.url-row { display: flex; gap: 6px; padding: 10px 12px 0; }
.url-input {
  flex: 1; min-width: 0; padding: 6px 9px;
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 7px;
  color: var(--text, #eee); font-size: 12.5px; outline: none;
}
.url-input:focus { border-color: color-mix(in oklch, var(--gold) 40%, var(--line)); }
.url-add {
  flex: none; padding: 5px 12px; border: 1px solid var(--line); border-radius: 7px;
  background: transparent; color: var(--muted); font-size: 11.5px; cursor: pointer;
  transition: color 150ms, border-color 150ms, background 150ms;
}
.url-add:hover:not(:disabled) { color: var(--ink); border-color: var(--line-strong, var(--line)); }
.url-add:disabled { opacity: 0.45; cursor: not-allowed; }

.hint {
  margin: 8px 12px 0; padding: 8px 10px;
  border: 1px solid color-mix(in oklch, var(--line) 70%, transparent); border-radius: 7px;
  color: var(--dim); font-size: 10.5px; line-height: 1.55;
  background: color-mix(in oklch, var(--panel2) 55%, transparent);
}

.asset-list { flex: 1; overflow-y: auto; padding: 8px 8px 12px; }
.empty { padding: 18px 10px; text-align: center; color: var(--dim); font-size: 11.5px; }

.asset-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 8px; margin: 2px 2px; border-radius: 7px;
  transition: background 140ms var(--ease);
}
.asset-row:hover { background: color-mix(in oklch, var(--ink) 5%, transparent); }
.play {
  flex: none; width: 26px; height: 26px; border-radius: 6px;
  border: 1px solid var(--line); background: transparent; color: var(--muted);
  cursor: pointer; display: grid; place-items: center; padding: 0;
  transition: color 140ms, border-color 140ms, background 140ms;
}
.play svg { width: 10px; height: 10px; }
.play:hover { color: var(--gold); border-color: color-mix(in oklch, var(--gold) 40%, var(--line)); background: var(--gold-soft); }
.info { flex: 1; min-width: 0; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.name { font-size: 12.5px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--dim); }
.src { padding: 0 5px; border-radius: 3px; font-weight: 600; }
.src.upload { color: var(--cyan, #7dd3fc); background: color-mix(in oklch, var(--cyan, #7dd3fc) 12%, transparent); }
.src.url { color: var(--violet, #a78bfa); background: color-mix(in oklch, var(--violet, #a78bfa) 12%, transparent); }
.op {
  flex: none; width: 22px; height: 22px; border: none; border-radius: 5px;
  background: transparent; color: var(--muted); cursor: pointer; font-size: 12px;
  opacity: 0; transition: opacity 130ms, background 130ms, color 130ms;
}
.asset-row:hover .op { opacity: 0.75; }
.op:hover { opacity: 1 !important; background: color-mix(in oklch, var(--ink) 8%, transparent); color: var(--ink); }
.op.danger:hover { color: var(--bad); }

.preview-mask {
  position: fixed; inset: 0; z-index: 9500;
  background: color-mix(in oklch, var(--bg) 82%, transparent);
  backdrop-filter: blur(6px);
  display: grid; place-items: center;
}
.preview-box {
  width: min(760px, 92vw); border-radius: 12px; overflow: hidden;
  background: var(--panel); border: 1px solid var(--line);
  box-shadow: 0 24px 60px oklch(0.03 0.02 278 / 0.4);
}
.preview-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; font-size: 12.5px; color: var(--ink);
  border-bottom: 1px solid var(--line);
}
.close { background: transparent; border: none; color: var(--muted); font-size: 15px; cursor: pointer; padding: 0 4px; }
.close:hover { color: var(--ink); }
.preview-video { display: block; width: 100%; max-height: 62vh; background: #000; }
</style>
