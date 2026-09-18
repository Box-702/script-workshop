<script setup>
// =====================================================================
// VideoWorkbench.vue —— 视频制作工作台
//
// 流程：摄影指导提出 Prompt → 人工编辑/批准 → 提交视频任务 →
// 可选的成片审批。分镜生成串行推进，前镜成片自动作为后镜接力参考。
// =====================================================================

import { computed, onMounted, onUnmounted, ref } from 'vue'
import ShotList from './ShotList.vue'
import VideoPlayer from './VideoPlayer.vue'
import PromptEditor from './PromptEditor.vue'
import {
  store, loadShots, loadVideoJobs, submitVideoJob, playVideo, closeVideo, openPromptEditor,
  closePromptEditor, saveShotPrompt, setVideoMode, setVideoResolution, startVideoBatch,
  pollVideoBatch, batchCommand,
} from '../../stores/app'

const RESOLUTIONS = [
  { value: '', label: '默认（768P）' },
  { value: '480P', label: '480P（最快）' },
  { value: '768P', label: '768P' },
  { value: '2K', label: '2K（最清晰）' },
]

const batch = computed(() => store.videoBatch)
const running = computed(() => batch.value?.status === 'running')
const awaiting = computed(() => batch.value?.status === 'awaiting_approval')
const progressText = computed(() => {
  const b = batch.value
  if (!b) return ''
  return `${Math.min(b.current_index + 1, b.total)} / ${b.total} 镜`
})
const promptCount = computed(() => {
  const prompts = store.shots.filter((shot) => shot.video_prompt)
  return {
    total: prompts.length,
    approved: prompts.filter((shot) => shot.prompt_status === 'approved').length,
    pending: prompts.filter((shot) => shot.prompt_status !== 'approved').length,
  }
})

// 审批预览：当前镜最新的成功视频
const currentShot = computed(() => store.shots.find((s) => s.id === batch.value?.current_shot_id) || null)
const currentVideoUrl = computed(() => {
  const sid = batch.value?.current_shot_id
  if (!sid) return ''
  const jobs = (store.videoJobs || [])
    .filter((j) => j.shot_id === sid && j.status === 'succeeded' && j.video_url)
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
  return jobs[0]?.video_url || ''
})

const starting = ref(false)
async function onStart() {
  starting.value = true
  try {
    await startVideoBatch()
  } finally {
    starting.value = false
  }
}

// 轮询：批次进行中每 3 秒刷新进度；组件挂载时也拉一次镜头与任务。
let timer = null
onMounted(async () => {
  await Promise.all([loadShots(), loadVideoJobs(), pollVideoBatch()])
  timer = setInterval(() => {
    if (running.value || awaiting.value) pollVideoBatch()
  }, 3000)
})
onUnmounted(() => clearInterval(timer))

async function onPromptReview(payload) {
  await saveShotPrompt(payload, payload.decision, payload.prompt_review_note)
}
</script>

<template>
  <div class="workbench">
    <!-- 控制栏：模式 / 分辨率 / 启动 -->
    <div class="ctrl">
      <div class="ctrl-group">
        <span class="ctrl-label">成片审批</span>
        <div class="seg">
          <button
            :class="['seg-btn', { active: store.videoMode === 'auto' }]"
            title="Prompt 批准后一次跑完全部镜头"
            @click="setVideoMode('auto')"
          >自动出片</button>
          <button
            :class="['seg-btn', { active: store.videoMode === 'approval' }]"
            title="每镜完成后暂停，预览后决定继续/重跑/终止"
            @click="setVideoMode('approval')"
          >逐镜审批</button>
        </div>
      </div>

      <div class="ctrl-group">
        <span class="ctrl-label">清晰度</span>
        <select
          class="res-select"
          :value="store.videoResolution"
          @change="setVideoResolution($event.target.value)"
        >
          <option v-for="r in RESOLUTIONS" :key="r.value" :value="r.value">{{ r.label }}</option>
        </select>
      </div>

      <button
        class="start-btn"
        :disabled="starting || running || !promptCount.approved"
        @click="onStart"
      >
        {{ running ? '批次进行中…' : `生成已批准镜头（${promptCount.approved}）` }}
      </button>
    </div>

    <div class="prompt-gate">
      <div>
        <strong>Prompt 人工审阅</strong>
        <span>摄影指导只提供草稿，批准后才会产生视频费用。</span>
      </div>
      <div class="prompt-count">
        <span class="approved">{{ promptCount.approved }} 已批准</span>
        <span v-if="promptCount.pending">{{ promptCount.pending }} 待处理</span>
        <span v-else-if="promptCount.total">全部已批准</span>
      </div>
    </div>

    <PromptEditor
      v-if="store.editingPrompt"
      :shot="store.editingPrompt"
      @close="closePromptEditor"
      @review="onPromptReview"
    />

    <!-- 批次进度 / 审批面板 -->
    <div v-if="batch && batch.status !== 'none'" class="batch" :class="'batch-' + batch.status">
      <div class="batch-head">
        <span class="batch-status">
          <template v-if="batch.status === 'running'">生成中 {{ progressText }}</template>
          <template v-else-if="awaiting">等待审批 {{ progressText }}</template>
          <template v-else-if="batch.status === 'done'">批次完成（{{ batch.total }} 镜）</template>
          <template v-else-if="batch.status === 'failed'">批次失败</template>
          <template v-else-if="batch.status === 'aborted'">已终止</template>
        </span>
        <span v-if="currentShot" class="batch-shot">{{ currentShot.subject || currentShot.id }}</span>
      </div>
      <div v-if="batch.error" class="batch-error">{{ batch.error }}</div>

      <!-- 审批预览 -->
      <div v-if="awaiting" class="review">
        <video v-if="currentVideoUrl" :src="currentVideoUrl" controls class="review-video" />
        <div v-else class="review-empty">成片地址加载中…</div>
        <div class="review-actions">
          <button class="rv ok" @click="batchCommand('approve')">✓ 通过，下一镜</button>
          <button class="rv" @click="batchCommand('reroll')">↻ 重跑本镜</button>
          <button class="rv danger" @click="batchCommand('abort')">✕ 终止批次</button>
        </div>
      </div>
      <div v-else-if="running || batch.status === 'failed' || batch.status === 'aborted'" class="review-actions">
        <button v-if="running" class="rv danger" @click="batchCommand('abort')">终止批次</button>
        <button v-if="batch.status === 'failed'" class="rv" @click="batchCommand('reroll')">重跑当前镜</button>
      </div>
    </div>

    <!-- 镜头列表 -->
    <ShotList
      :shots="store.shots"
      :scenes="store.viewerScript?.scenes || []"
      @generate-video="submitVideoJob"
      @generate-all="onStart"
      @play-video="playVideo"
      @edit-prompt="openPromptEditor"
      @refresh="loadShots()"
    />

    <!-- 单镜播放器（store 控制） -->
    <VideoPlayer
      v-if="store.playingVideo"
      :url="store.playingVideo.url"
      :title="store.playingVideo.title"
      :meta="store.playingVideo.meta"
      @close="closeVideo()"
    />
  </div>
</template>

<style scoped>
.workbench { padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
.ctrl { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.ctrl-group { display: flex; align-items: center; gap: 8px; }
.ctrl-label { font-size: 11px; color: var(--dim); font-weight: 600; }
.seg { display: flex; border: 1px solid var(--line); border-radius: 9px; overflow: hidden; }
.seg-btn {
  background: transparent; border: none; color: var(--muted);
  padding: 5px 12px; font-size: 12px; cursor: pointer; transition: all 150ms;
}
.seg-btn + .seg-btn { border-left: 1px solid var(--line); }
.seg-btn.active { background: var(--select); color: var(--ink); font-weight: 600; }
.res-select {
  background: var(--panel2); color: var(--ink); border: 1px solid var(--line);
  border-radius: 8px; padding: 5px 8px; font-size: 12px;
}
.start-btn {
  margin-left: auto; background: var(--ok); color: var(--on-accent); border: none;
  border-radius: 9px; padding: 8px 16px; font-size: 12.5px; font-weight: 650; cursor: pointer;
}
.start-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.prompt-gate {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 10px 12px; border: 1px solid var(--line); border-radius: 9px;
  background: color-mix(in oklch, var(--panel2) 70%, transparent);
}
.prompt-gate strong { display: block; color: var(--ink); font-size: 12px; }
.prompt-gate span { color: var(--dim); font-size: 11px; }
.prompt-count { display: flex; gap: 10px; flex: none; font-size: 11px; }
.prompt-count .approved { color: var(--ok); }

.batch { border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; background: var(--panel2); }
.batch-awaiting_approval { border-color: color-mix(in oklch, var(--warn) 45%, var(--line)); }
.batch-head { display: flex; align-items: center; gap: 12px; }
.batch-status { font-size: 12.5px; font-weight: 600; color: var(--ink); }
.batch-shot { font-size: 11.5px; color: var(--dim); }
.batch-error { margin-top: 6px; font-size: 11.5px; color: var(--danger, #e5484d); }

.review { margin-top: 10px; }
.review-video { width: 100%; max-width: 560px; border-radius: 10px; background: #000; }
.review-empty { font-size: 12px; color: var(--dim); padding: 8px 0; }
.review-actions { display: flex; gap: 8px; margin-top: 10px; }
.rv {
  border: 1px solid var(--line); background: var(--panel2); color: var(--ink);
  border-radius: 9px; padding: 6px 14px; font-size: 12.5px; cursor: pointer;
}
.rv.ok { background: var(--ok); color: var(--on-accent); border-color: transparent; font-weight: 600; }
.rv.danger { color: var(--danger, #e5484d); }

@media (max-width: 620px) {
  .prompt-gate { align-items: flex-start; flex-direction: column; gap: 6px; }
}
</style>
