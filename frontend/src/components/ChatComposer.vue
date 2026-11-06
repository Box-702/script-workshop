<script setup>
// =====================================================================
// ChatComposer.vue —— 工作区输入区
//
// 卡片本体与首页共用 ComposerCard.vue；这里只管工作区特有的：
// 粘贴/上传图片、上下文提示、生成阶段状态。
// 图片：选文件 / Ctrl+V 粘贴截图 → 立即上传（字节入库）→ 预览可删除，
//       发送时随消息带上图片 id，模型本轮识图、之后每轮仍在上下文里。
// 交互：Enter 发送 / Shift+Enter 换行（含输入法 composing 保护）。
// =====================================================================

import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { store, sendMessage, clearHint, loadModelStatus, notify } from '../stores/app'
import { uploadChatImage } from '../api'
import ComposerCard from './ComposerCard.vue'

const text = ref('')
const card = ref(null)

// ---- 图片上传（对话多模态） ----
const attachedImages = ref([])   // [{ id, url, name, uploading }]
const uploadingCount = ref(0)
const fileInput = ref(null)

const hasImages = computed(() => attachedImages.value.some((i) => i.id))
const canSend = computed(() => (!!text.value.trim() || hasImages.value) && !store.streaming && uploadingCount.value === 0)

// 当前对话模型（胶囊；点击打开设置里的模型配置）
const modelLabel = computed(() => {
  const m = store.modelInfo
  if (!m?.available) return '未配置模型'
  return m.name || m.provider
})
const specLabel = computed(() => {
  const res = store.videoResolution || '768P'
  const aspect = store.videoAspect || '9:16'
  return `${res} · ${aspect}`
})
const contextText = computed(() => {
  if (store.hint) return store.hint
  return store.pid ? '准备好继续创作' : '直接从一句话开始'
})
const statusText = computed(() => (store.streaming ? store.streamingStage || '正在处理' : ''))

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
  if (idx >= 0) {
    URL.revokeObjectURL(item.preview)
    attachedImages.value.splice(idx, 1)
  }
}

function onPaste(e) {
  // 聚焦在输入框时的粘贴截图/复制图片才收；其他场景（如剧本编辑器）不抢。
  const ta = card.value?.$el?.querySelector('textarea')
  if (!ta || !(e.target === ta || ta.contains(e.target))) return
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
  sendMessage(t, imageIds)
}

function cycleResolution() {
  const opts = ['768P', '1080P']
  const cur = store.videoResolution || '768P'
  const i = opts.indexOf(cur)
  store.setVideoResolution(opts[(i + 1) % opts.length])
}

// 开始页主按钮 / 编辑态空态的「输入我的想法」：聚焦输入框
watch(() => store.focusSeq, () => nextTick(() => card.value?.focus()))
watch(() => store.convId, () => nextTick(() => card.value?.focus()))

// 示例模板把文本填进输入框（不自动发送，由用户确认后发出）。
watch(() => store.draftSeq, () => {
  if (!store.draft) return
  text.value = store.draft
  nextTick(() => card.value?.focus())
})
</script>

<template>
  <div class="composer">
    <input
      ref="fileInput"
      type="file"
      accept="image/png,image/jpeg,image/webp,image/gif"
      multiple
      hidden
      @change="onFileChosen"
    />
    <ComposerCard
      ref="card"
      v-model:text="text"
      placeholder="描述你的故事想法"
      :model-label="modelLabel"
      :spec-label="specLabel"
      :context-text="contextText"
      :status-text="statusText"
      :can-send="canSend"
      :busy="store.streaming"
      @send="send"
      @open-settings="store.showSettings = true"
      @cycle-spec="cycleResolution"
      @open-library="store.leftOpen = true"
      @focus-input="clearHint"
    >
      <template #menu="{ close }">
        <button class="cc-menu-item" type="button" role="menuitem" @click.stop="close(); pickImages()">
          本地上传
        </button>
        <button class="cc-menu-item" type="button" role="menuitem" @click.stop="close(); store.leftOpen = true">
          资产库
        </button>
        <button class="cc-menu-item" type="button" role="menuitem" @click.stop="close(); store.leftOpen = true">
          主体库（支持音色）
        </button>
        <button class="cc-menu-item" type="button" role="menuitem" @click.stop="close(); store.leftOpen = true">
          音色库
        </button>
      </template>

      <template #attachments>
        <div v-if="attachedImages.length" class="image-strip" aria-label="待发送图片">
          <div v-for="item in attachedImages" :key="item.preview" class="image-thumb" :class="{ uploading: item.uploading }">
            <img :src="item.preview" alt="待发送图片" />
            <button class="thumb-remove" aria-label="移除图片" @click.stop="removeImage(item)">
              ✕
            </button>
            <span v-if="item.uploading" class="thumb-mask">上传中</span>
          </div>
        </div>
      </template>
    </ComposerCard>
  </div>
</template>

<style scoped>
.composer {
  padding: var(--space-3) clamp(var(--space-4), 3vw, var(--space-6)) var(--space-4);
  background: transparent;
}

/* 待发送图片 */
.image-strip { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.image-thumb {
  position: relative; width: 56px; height: 56px; border-radius: 10px;
  overflow: hidden; border: 1px solid var(--line);
}
.image-thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-remove {
  position: absolute; top: 2px; right: 2px; width: 18px; height: 18px;
  border: 0; border-radius: 50%; display: grid; place-items: center;
  background: rgba(0, 0, 0, .66); color: #fff; cursor: pointer; font-size: 10px; line-height: 1;
}
.thumb-mask {
  position: absolute; inset: 0; display: grid; place-items: center;
  background: rgba(0, 0, 0, .55); font-size: 11px; color: rgba(255, 255, 255, .85);
}

/* 菜单条目（挂在 ComposerCard 的插槽里） */
.cc-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 255, 255, 0.86);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
}

.cc-menu-item:hover {
  background: rgba(255, 255, 255, 0.09);
  color: #fff;
}
</style>
