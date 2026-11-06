<script setup>
// =====================================================================
// HomeComposer.vue —— 首页主输入卡片
//
// 形制：一张大卡片 = 顶部「＋ 按钮 + 多行输入」+ 底部「参数胶囊 + 主行动按钮」。
// ＋ 按钮点开素材菜单（本地上传 / 资产库 / 主体库 / 音色库）。
// 底部胶囊对应真实状态：产出目标、对话模型、参考素材、视频规格。
// =====================================================================

import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { store, sendMessage, loadModelStatus, notify, setHint } from '../stores/app'
import { uploadChatImage } from '../api'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  /** 产出目标：决定发送时给 Agent 的意图前缀 */
  goal: { type: String, default: 'novel-to-drama' },
})
const emit = defineEmits(['pick-library'])

const input = ref(null)
const text = ref('')
const menuOpen = ref(false)
const fileInput = ref(null)
const attachedImages = ref([])
const uploadingCount = ref(0)

const GOALS = [
  { id: 'novel-to-drama', label: '小说改编' },
  { id: 'storyboard', label: '分镜设计' },
  { id: 'production', label: '成片交付' },
]

const MENU = [
  { id: 'upload', label: '本地上传' },
  { id: 'assets', label: '资产库' },
  { id: 'cast', label: '主体库（支持音色）' },
  { id: 'voice', label: '音色库' },
]

const SPEC_RESOLUTIONS = ['768P', '1080P']
const SPEC_ASPECTS = ['9:16', '16:9', '1:1']

const goalLabel = computed(() => (GOALS.find((g) => g.id === props.goal) || GOALS[0]).label)
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
const canSend = computed(() => (!!text.value.trim() || attachedImages.value.some((i) => i.id))
  && !store.streaming && uploadingCount.value === 0)

onMounted(() => {
  loadModelStatus()
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => document.removeEventListener('click', onDocClick))

function onDocClick(e) {
  if (!menuOpen.value) return
  if (e.target.closest && e.target.closest('.hc-plus-wrap')) return
  menuOpen.value = false
}

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function pick(item) {
  menuOpen.value = false
  if (item.id === 'upload') {
    fileInput.value?.click()
    return
  }
  // 资产 / 主体 / 音色都要落到具体作品上，没有作品就先去建一个
  if (!store.pid) {
    store.showNewProject = true
    setHint('先新建作品，再挂载素材')
    return
  }
  emit('pick-library', item.id)
}

function onFileChosen(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''
  for (const f of files) addImage(f)
}

async function addImage(file) {
  if (!file.type.startsWith('image/')) {
    notify('目前只支持上传图片')
    return
  }
  const item = { id: null, url: '', name: file.name, uploading: true, preview: URL.createObjectURL(file) }
  attachedImages.value.push(item)
  uploadingCount.value++
  try {
    const res = await uploadChatImage(file)
    item.id = res.id
    item.url = res.url
  } catch (e) {
    notify(`图片上传失败：${e.message}`)
    const i = attachedImages.value.indexOf(item)
    if (i >= 0) attachedImages.value.splice(i, 1)
  } finally {
    item.uploading = false
    uploadingCount.value--
  }
}

function removeImage(item) {
  const i = attachedImages.value.indexOf(item)
  if (i >= 0) {
    URL.revokeObjectURL(item.preview)
    attachedImages.value.splice(i, 1)
  }
}

function send() {
  const t = text.value.trim()
  if ((!t && !attachedImages.value.some((i) => i.id)) || store.streaming || uploadingCount.value > 0) return
  const imageIds = attachedImages.value.filter((i) => i.id).map((i) => i.id)
  attachedImages.value.forEach((i) => URL.revokeObjectURL(i.preview))
  text.value = ''
  attachedImages.value = []
  if (input.value) input.value.style.height = 'auto'
  // 产出目标作为意图前缀，让 Agent 一上来就知道这轮要什么
  const prefix = goalLabel.value ? `【${goalLabel.value}】` : ''
  sendMessage(prefix + t, imageIds)
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

function cycleResolution() {
  const cur = store.videoResolution || '768P'
  const i = SPEC_RESOLUTIONS.indexOf(cur)
  store.setVideoResolution(SPEC_RESOLUTIONS[(i + 1) % SPEC_RESOLUTIONS.length])
}

function cycleAspect() {
  const cur = store.videoAspect || '9:16'
  const i = SPEC_ASPECTS.indexOf(cur)
  store.setVideoAspect(SPEC_ASPECTS[(i + 1) % SPEC_ASPECTS.length])
}

function openModelSettings() {
  store.showSettings = true
}
</script>

<template>
  <div class="hc">
    <div class="hc-card" @click="input?.focus()">
      <!-- 上：＋ 按钮 + 输入 -->
      <div class="hc-top">
        <div class="hc-plus-wrap">
          <button
            class="hc-plus"
            type="button"
            aria-label="添加素材"
            :aria-expanded="menuOpen"
            @click.stop="toggleMenu"
          >
            <AppIcon name="plus" />
          </button>
          <Transition name="pop">
            <div v-if="menuOpen" class="hc-menu" role="menu">
              <button
                v-for="item in MENU"
                :key="item.id"
                class="hc-menu-item"
                type="button"
                role="menuitem"
                @click.stop="pick(item)"
              >{{ item.label }}</button>
            </div>
          </Transition>
        </div>

        <div class="hc-input-wrap">
          <textarea
            ref="input"
            v-model="text"
            class="hc-text"
            rows="1"
            placeholder="描述画面，也可上传图片、视频、主体或音色，进行参考生成等。支持使用 @ 快速调用参考素材。内容将由 AI 生成。"
            @keydown="onKeydown"
            @input="autoSize"
          ></textarea>
          <div v-if="attachedImages.length" class="hc-strip">
            <div v-for="item in attachedImages" :key="item.preview" class="hc-thumb">
              <img :src="item.preview" alt="待发送图片" />
              <button class="hc-thumb-x" type="button" aria-label="移除图片" @click.stop="removeImage(item)">
                <AppIcon name="close" />
              </button>
              <span v-if="item.uploading" class="hc-thumb-mask">上传中</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 下：参数胶囊 + 主行动 -->
      <div class="hc-bottom">
        <div class="hc-pills">
          <button class="hc-pill" type="button" @click.stop="$emit('goal', goal)">
            <AppIcon name="film" />
            <span>{{ goalLabel }}</span>
            <AppIcon name="chevron-down" class="hc-chev" />
          </button>
          <button class="hc-pill" type="button" @click.stop="openModelSettings">
            <AppIcon name="gear" />
            <span>{{ modelLabel }}</span>
            <AppIcon name="chevron-down" class="hc-chev" />
          </button>
          <button class="hc-pill" type="button" @click.stop="$emit('pick-library', 'assets')">
            <AppIcon name="folder" />
            <span>全能参考</span>
            <AppIcon name="chevron-down" class="hc-chev" />
          </button>
          <button class="hc-pill" type="button" @click.stop="cycleResolution">
            <AppIcon name="play" />
            <span>{{ specLabel }}</span>
            <AppIcon name="chevron-down" class="hc-chev" />
          </button>
        </div>
        <button class="hc-cta" type="button" :disabled="!canSend" @click.stop="send">开拍</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hc {
  width: 100%;
  max-width: 1040px;
  margin: 0 auto;
}

.hc-card {
  position: relative;
  border-radius: 20px;
  padding: 14px 14px 12px;
  background: rgba(255, 255, 255, 0.055);
  border: 1px solid rgba(255, 255, 255, 0.11);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.42);
  transition: border-color 0.18s ease, background 0.18s ease;
}

.hc-card:focus-within {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.075);
}

.hc-top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.hc-plus-wrap {
  position: relative;
  flex: none;
}

.hc-plus {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.07);
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.hc-plus:hover {
  background: rgba(255, 255, 255, 0.17);
  color: #fff;
}

.hc-menu {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  min-width: 190px;
  padding: 6px;
  border-radius: 12px;
  background: rgba(22, 22, 28, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.55);
  z-index: 30;
}

.hc-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 255, 255, 0.86);
  font-size: 13px;
  cursor: pointer;
}

.hc-menu-item:hover {
  background: rgba(255, 255, 255, 0.09);
  color: #fff;
}

.hc-input-wrap {
  flex: 1;
  min-width: 0;
  padding-top: 14px;
}

.hc-text {
  width: 100%;
  min-height: 84px;
  max-height: 200px;
  resize: none;
  border: 0;
  outline: 0;
  background: transparent;
  color: rgba(255, 255, 255, 0.94);
  font-size: 14px;
  line-height: 1.65;
  font-family: inherit;
}

.hc-text::placeholder {
  color: rgba(255, 255, 255, 0.34);
}

.hc-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.hc-thumb {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.14);
}

.hc-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hc-thumb-x {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.66);
  color: #fff;
  cursor: pointer;
}

.hc-thumb-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.55);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.85);
}

.hc-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}

.hc-pills {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hc-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 11px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.78);
  font-size: 12.5px;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
}

.hc-pill:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.18);
}

.hc-chev {
  opacity: 0.5;
}

.hc-cta {
  flex: none;
  min-width: 96px;
  height: 38px;
  padding: 0 22px;
  border: 0;
  border-radius: 9px;
  background: linear-gradient(135deg, #86ef7d 0%, #4ade80 45%, #22c55e 100%);
  color: #06210f;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(34, 197, 94, 0.28);
  transition: filter 0.16s ease, transform 0.16s ease, opacity 0.16s ease;
}

.hc-cta:hover:not(:disabled) {
  filter: brightness(1.06);
}

.hc-cta:active:not(:disabled) {
  transform: translateY(1px);
}

.hc-cta:disabled {
  opacity: 0.42;
  cursor: not-allowed;
  box-shadow: none;
}

.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
