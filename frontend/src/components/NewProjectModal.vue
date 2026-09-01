<script setup>
// =====================================================================
// NewProjectModal.vue —— 新建剧本弹窗
//
// 表单：剧名 + 改编类型 + 原著来源（上传 .txt/.md/.docx 或粘贴原文）。
// 支持点击选择与拖拽文件；提交走 /api/projects/import（FormData）。
// 体验：ESC/点遮罩关闭、打开时过渡 + 自动聚焦剧名、提交中禁用按钮。
// =====================================================================

import { ref, watch, nextTick, onUnmounted } from 'vue'
import { store, submitNewProject } from '../stores/app'

const ADAPT_TYPES = [
  { value: 'short_drama', label: '短剧' },
  { value: 'film', label: '电影' },
  { value: 'series', label: '剧集' },
  { value: 'stage', label: '舞台剧' },
  { value: 'other', label: '自定义' },
]
const ACCEPT = /\.(txt|md|markdown|docx)$/i

const title = ref('')
const adapt = ref('short_drama')
const raw = ref('')
const file = ref(null)          // 选中的 File 对象
const dropText = ref('点击选择或拖入 .txt / .md / .docx 文件')
const dragOver = ref(false)
const err = ref('')
const fileInput = ref(null)
const titleInput = ref(null)    // 打开时自动聚焦
const submitting = ref(false)   // 提交中（导入需要分析，给足反馈）

// ESC 关闭（提交中不关闭）
function onKey(e) {
  if (e.key === 'Escape' && store.showNewProject && !submitting.value) store.showNewProject = false
}

// 每次打开：重置表单 + 聚焦剧名；关闭时移除键盘监听
watch(() => store.showNewProject, (open) => {
  if (open) {
    title.value = ''; raw.value = ''; file.value = null; err.value = ''; submitting.value = false
    dropText.value = '点击选择或拖入 .txt / .md / .docx 文件'
    nextTick(() => titleInput.value?.focus())
    window.addEventListener('keydown', onKey)
  } else {
    window.removeEventListener('keydown', onKey)
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKey))

/** 校验并记录选中的文件（点击与拖拽共用）。 */
function pickFile(f) {
  if (!ACCEPT.test(f.name)) {
    dropText.value = `⚠️ 不支持 ${f.name}，请选择 .txt/.md/.docx`
    file.value = null
    return
  }
  file.value = f
  dropText.value = `📄 ${f.name}（${(f.size / 1024).toFixed(1)} KB）`
}

function onFileChange(e) { if (e.target.files.length) pickFile(e.target.files[0]) }
function onDrop(e) {
  dragOver.value = false
  if (e.dataTransfer.files.length) pickFile(e.dataTransfer.files[0])
}

/** 提交表单（校验 + 调 store 动作，错误就地显示）。 */
async function submit() {
  if (submitting.value) return
  err.value = ''
  if (!title.value.trim()) { err.value = '请填写剧名'; return }
  if (!file.value && !raw.value.trim()) { err.value = '请上传文件或粘贴原文'; return }
  submitting.value = true
  try {
    await submitNewProject({ title: title.value.trim(), adapt: adapt.value, file: file.value, raw: raw.value.trim() })
  } catch (e) { err.value = '创建失败：' + e.message } finally { submitting.value = false }
}
</script>

<template>
  <!-- 点遮罩关闭。不用 Vue Transition：其元素移除依赖 rAF/transitionend，
       在后台标签页会被冻结导致关不掉；这里用纯 CSS 入场动画（仅视觉，
       不影响 DOM 移除时机），v-if 关闭即瞬时移除，任何环境都可靠。 -->
  <div v-if="store.showNewProject" class="modal-backdrop" @click.self="!submitting && (store.showNewProject = false)">
    <div class="modal" role="dialog" aria-label="新建剧本">
      <h3>新建剧本 <span class="muted" style="font-size: 12px; font-weight: 400">＝ 新项目</span></h3>
      <div class="sub">导入原著（.txt / .md / .docx）或粘贴原文，创建后自动建立项目知识库（同类走向 / 写作手法 / 作者风格）</div>

      <label>剧名</label>
      <input ref="titleInput" v-model="title" placeholder="例如：雨夜" style="width: 100%" @keydown.enter="submit" />

      <label>改编类型</label>
      <select v-model="adapt" style="width: 100%">
        <option v-for="t in ADAPT_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>

      <label>原著文件（可拖拽）</label>
      <div
        class="drop" :class="{ drag: dragOver }"
        @click="fileInput.click()"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >{{ dropText }}</div>
      <input ref="fileInput" type="file" accept=".txt,.md,.markdown,.docx" style="display: none" @change="onFileChange" />

      <label>或直接粘贴原文</label>
      <textarea v-model="raw" placeholder="粘贴小说 / 剧本原文（3 段以上最佳）"></textarea>

      <div v-if="err" class="err">⚠️ {{ err }}</div>

      <div class="foot">
        <button class="ghost" :disabled="submitting" @click="store.showNewProject = false">取消</button>
        <button :disabled="submitting" @click="submit">{{ submitting ? '创建中…' : '创建剧本' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: oklch(0 0 0 / 0.55);
  display: flex; align-items: center; justify-content: center; z-index: 50;
}
.modal {
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  width: 520px; max-width: 94vw; max-height: 88vh; overflow-y: auto;
  padding: 18px 20px; box-shadow: 0 20px 60px oklch(0 0 0 / 0.5);
}
h3 { margin: 0 0 4px; font-size: 16px; }
.sub { color: var(--muted); font-size: 12px; margin-bottom: 14px; }
label { display: block; font-size: 12px; color: var(--muted); margin: 12px 0 4px; }
.drop {
  border: 1.5px dashed var(--line); border-radius: 10px; padding: 18px;
  text-align: center; color: var(--muted); font-size: 12.5px; cursor: pointer;
  transition: border-color var(--dur) var(--ease), color var(--dur) var(--ease), background-color var(--dur) var(--ease);
}
.drop:hover, .drop.drag { border-color: var(--accent); color: var(--ink); }
.drop.drag { background: var(--accent-soft); }
.foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
textarea { width: 100%; min-height: 110px; }
.err { color: var(--bad); font-size: 12px; margin-top: 8px; }

/* 入场动画：遮罩淡入 + 弹窗轻缩放（纯视觉，不影响关闭的可靠性） */
.modal-backdrop { animation: fade-in 180ms var(--ease); }
.modal { animation: pop-in 180ms var(--ease); }
@keyframes fade-in { from { opacity: 0; } }
@keyframes pop-in { from { opacity: 0; transform: scale(0.96) translateY(6px); } }
</style>
