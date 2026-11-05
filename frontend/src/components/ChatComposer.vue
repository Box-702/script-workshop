<script setup>
// =====================================================================
// ChatComposer.vue —— 底部输入区
//
// 结构：圆角容器 = 文本域 + 图片预览条 + 底部工具行
//   工具行左：「＋ 导入文档」（txt/md/docx/pdf）+ 图片按钮 + 上下文提示
//   工具行右：生成中的阶段状态条（aria-live）+ 发送按钮「开始生成」
// 图片：选文件 / Ctrl+V 粘贴截图 → 立即上传（字节入库）→ 预览可删除，
//       发送时随消息带上图片 id，模型本轮识图、之后每轮仍在上下文里。
// 交互：Enter 发送 / Shift+Enter 换行（含输入法 composing 保护）；
//       所有点击目标 ≥44px；发送按钮有 hover/active/disabled。
// =====================================================================

import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { store, sendMessage, focusComposer, clearHint, loadModelStatus, notify } from '../stores/app'
import { uploadChatImage } from '../api'
import AppIcon from './AppIcon.vue'

const input = ref(null)
const text = ref('')

// ---- 图片上传（对话多模态） ----
const attachedImages = ref([])   // [{ id, url, name, uploading }]
const uploadingCount = ref(0)
const fileInput = ref(null)

const hasImages = computed(() => attachedImages.value.some((i) => i.id))
const canSend = computed(() => (!!text.value.trim() || hasImages.value) && !store.streaming && uploadingCount.value === 0)

// 当前对话模型（工具行徽标；点击打开设置里的模型配置）
const modelChip = computed(() => {
  const m = store.modelInfo
  if (!m?.available) return null
  const short = { DeepSeek: 'DS' }[m.provider] || m.provider
  return { label: `${short} · ${m.name}` }
})
onMounted(() => {
  loadModelStatus()
  document.addEventListener('paste', onPaste)
})
onUnmounted(() => document.removeEventListener('paste', onPaste))

async function addImageFiles(files) {
  const images = [...files].filter((f) => f.type.startsWith('image/'))
  if (!images.length) return
  for (const file of images) {
    const item = reactive({ id: null, url: '', name: file.name, uploading: true, preview: URL.createObjectURL(file) })
    attachedImages.value.push(item)
    if (attachedImages.value.length > 4) attachedImages.value.splice(0, attachedImages.value.length - 4)
    uploadingCount.value++
    try {
      const res = await uploadChatImage(file)
      item.id = res.id
      item.url = res.url
    } catch (e) {
      notify(`图片上传失败：${e.message}`)
      const idx = attachedImages.value.indexOf(item)
      if (idx >= 0) attachedImages.value.splice(idx, 1)
    } finally {
      item.uploading = false
      uploadingCount.value--
    }
  }
}

function pickImages() {
  fileInput.value?.click()
}

function onFileChosen(e) {
  addImageFiles(e.target.files || [])
  e.target.value = ''
}

function removeImage(item) {
  const idx = attachedImages.value.indexOf(item)
  if (idx >= 0) attachedImages.value.splice(idx, 1)
}

function onPaste(e) {
  // 聚焦在输入框时的粘贴截图/复制图片才收；其他场景（如剧本编辑器）不抢。
  if (!input.value || !(e.target === input.value || input.value.contains(e.target))) return
  const files = [...(e.clipboardData?.files || [])]
  if (files.length) {
    e.preventDefault()
    addImageFiles(files)
  }
}

function send() {
  const t = text.value.trim()
  if ((!t && !hasImages.value) || store.streaming || uploadingCount.value > 0) return
  const imageIds = attachedImages.value.filter((i) => i.id).map((i) => i.id)
  attachedImages.value.forEach((i) => URL.revokeObjectURL(i.preview))
  text.value = ''
  attachedImages.value = []
  input.value.style.height = 'auto'
  sendMessage(t, imageIds)
}

function onKeydown(e) {
  if (e.key !== 'Enter' || e.shiftKey) return
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  send()
}

function autoSize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(160, el.scrollHeight) + 'px'
}

// 开始页主按钮 / 编辑态空态的「输入我的想法」：聚焦输入框
watch(() => store.focusSeq, () => nextTick(() => input.value?.focus()))

watch(() => store.convId, () => nextTick(() => input.value?.focus()))

// 开始页示例模板把文本填进输入框（不自动发送，由用户确认后发出）。
watch(() => store.draftSeq, () => {
  if (!store.draft) return
  text.value = store.draft
  nextTick(() => {
    const el = input.value
    if (!el) return
    el.focus()
    el.style.height = 'auto'
    el.style.height = Math.min(160, el.scrollHeight) + 'px'
  })
})
</script>

<template>
  <div class="composer">
    <div class="input-box" @click="input?.focus()">
      <textarea
        ref="input"
        v-model="text"
        rows="1"
        placeholder="描述你的故事想法"
        aria-label="描述你的故事想法"
        @keydown="onKeydown"
        @input="autoSize"
        @focus="clearHint"
      ></textarea>
      <div v-if="attachedImages.length" class="image-strip" aria-label="待发送图片">
        <div v-for="item in attachedImages" :key="item.preview" class="image-thumb" :class="{ uploading: item.uploading }">
          <img :src="item.preview" alt="待发送图片" />
          <button class="thumb-remove" aria-label="移除图片" @click.stop="removeImage(item)">
            <AppIcon name="close" />
          </button>
          <span v-if="item.uploading" class="thumb-mask">上传中</span>
        </div>
      </div>
      <div class="toolbar">
        <div class="toolbar-left">
          <input
            ref="fileInput"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            hidden
            @change="onFileChosen"
          />
          <button
            class="tool-btn"
            title="添加图片（也可直接粘贴截图）"
            aria-label="添加图片"
            :disabled="store.streaming || attachedImages.length >= 4"
            @click.stop="pickImages"
          >
            <AppIcon name="image" />
          </button>
          <button
            v-if="modelChip"
            class="model-chip"
            title="当前对话模型 · 点击在设置中更换"
            @click.stop="store.showSettings = true"
          >{{ modelChip.label }}</button>
          <span class="composer-context">
            <span class="context-dot" :class="{ active: store.pid }"></span>
            <span v-if="store.hint" class="hint">{{ store.hint }}</span>
            <span v-else>{{ store.pid ? '准备好继续创作' : '直接从一句话开始' }}</span>
          </span>
        </div>
        <div class="toolbar-right">
          <!-- 阶段状态条：生成过程中展示当前阶段 -->
          <Transition name="stagefade">
            <span
              v-if="store.streaming"
              class="stage"
              role="status"
              aria-live="polite"
            >
              <span class="pulse" aria-hidden="true"></span>{{ store.streamingStage || '正在处理' }}
            </span>
          </Transition>
          <button
            class="send"
            :class="{ ready: canSend }"
            :disabled="!canSend"
            :aria-label="canSend ? '开始生成' : '输入内容后开始生成'"
            title="开始生成（Enter）"
            @click.stop="send"
          >
            <AppIcon name="send" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer { padding: var(--space-3) clamp(var(--space-4), 3vw, var(--space-6)) var(--space-4); background: transparent; }

/* 圆角容器：文本域 + 工具行（焦点光环走 --focus-ring 语义） */
.input-box {
  background: var(--panel);
  border: 1px solid var(--line); border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3) 7px; cursor: text;
  max-width: 900px; margin: 0 auto;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}
.input-box:focus-within {
  border-color: color-mix(in oklch, var(--gold) 40%, var(--line));
  box-shadow: 0 0 0 2px color-mix(in oklch, var(--gold) 14%, transparent);
}
textarea {
  display: block; width: 100%; min-height: 24px; max-height: 160px;
  line-height: var(--lh-body);
  background: transparent; border: none; padding: 2px 4px;
  font-size: var(--fs-lg); color: var(--ink); resize: none; font-family: inherit;
  overflow-y: auto;
}
textarea::placeholder { color: var(--dim); transition: color var(--dur) var(--ease); }
textarea:focus { outline: none; box-shadow: none; border: none; }
textarea:focus-visible { outline: none; }

/* 待发送图片预览条 */
.image-strip { display: flex; gap: var(--space-2); padding: var(--space-2) 4px 0; flex-wrap: wrap; }
.image-thumb {
  position: relative; width: 64px; height: 64px; border-radius: 8px; overflow: hidden;
  border: 1px solid var(--line);
}
.image-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.image-thumb.uploading img { opacity: .45; }
.thumb-remove {
  position: absolute; top: 2px; right: 2px; width: 18px; height: 18px;
  display: grid; place-items: center; border: none; border-radius: 50%;
  background: oklch(.2 .02 278 / .72); color: #fff; cursor: pointer; padding: 0;
}
.thumb-remove .app-ic { font-size: 9px; }
.thumb-mask {
  position: absolute; inset: auto 0 0 0; font-size: 10px; text-align: center;
  background: oklch(.2 .02 278 / .72); color: #fff; padding: 1px 0;
}

/* 图片按钮：与模型徽标同排的安静工具按钮 */
.tool-btn {
  width: 28px; height: 28px; padding: 0; border-radius: 7px;
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  display: inline-grid; place-items: center; flex: none;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.tool-btn .app-ic { font-size: 14px; }
.tool-btn:hover:not(:disabled) { color: var(--ink); border-color: var(--line-strong); }
.tool-btn:disabled { opacity: .4; cursor: default; }

/* 工具行 */
.toolbar { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) 2px 0; min-height: 44px; }
.toolbar-left { display: flex; align-items: center; gap: var(--space-2); flex: 1; min-width: 0; }
/* 导入文档：可视 36px，命中区扩到 44px */
/* 模型徽标：安静的文字 chip，点击进设置 */
.model-chip {
  height: 24px; padding: 0 8px; border-radius: 6px; flex: none;
  background: transparent; border: 1px solid var(--line); color: var(--muted);
  font-size: 10.5px; font-family: var(--mono); line-height: 1;
  display: inline-flex; align-items: center;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.model-chip:hover { color: var(--ink); border-color: var(--line-strong); }
.hint { color: var(--dim); font-size: var(--fs-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.composer-context { min-width: 0; display: inline-flex; align-items: center; gap: 7px; color: var(--dim); font-size: var(--fs-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.context-dot { width: 6px; height: 6px; flex: none; border-radius: 50%; background: var(--dim); }
.context-dot.active { background: var(--cyan); box-shadow: 0 0 10px color-mix(in oklch, var(--cyan) 60%, transparent); }
.toolbar-right { display: flex; align-items: center; gap: var(--space-2); flex: none; }

/* 阶段状态条 */
.stage {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--gold); font-size: var(--fs-sm); font-weight: 550;
  white-space: nowrap;
}
.pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--gold); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 0.3; transform: scale(0.9); } 50% { opacity: 1; transform: scale(1.1); } }
.stagefade-enter-active, .stagefade-leave-active { transition: opacity var(--dur-slow) var(--ease); }
.stagefade-enter-from, .stagefade-leave-to { opacity: 0; }

/* 发送按钮「开始生成」：44×44 命中区 */
.send {
  position: relative;
  width: 44px; height: 44px; padding: 0; border-radius: var(--radius-md);
  background: transparent; color: var(--dim);
  border: 1px solid transparent;
  display: inline-grid; place-items: center; flex: none;
  transition: background-color 200ms var(--ease), color 200ms var(--ease), border-color 200ms var(--ease);
}
.send .app-ic { font-size: 18px; transform: translateY(-0.5px); }
.send.ready {
  background: var(--accent);
  color: var(--on-accent);
}
.send.ready:hover:not(:disabled) { background: var(--accent-hover); }
.send.ready:active:not(:disabled) { background: color-mix(in oklch, var(--accent) 88%, black); }
.send:disabled { opacity: 0.45; cursor: default; }
</style>
