<template>
  <div class="shot-list">
    <div class="shot-header">
      <h4>🎬 镜头列表</h4>
      <div class="shot-actions">
        <button class="btn-small" @click="$emit('refresh')">刷新</button>
        <button class="btn-small ok" @click="$emit('generate-all')" v-if="shots.length">
          全部生成视频
        </button>
      </div>
    </div>

    <div v-if="!shots.length" class="empty-state">
      <p>还没有镜头数据</p>
      <p class="hint">请先在对话中说「拆镜头」或「设计镜头」</p>
    </div>

    <div v-else class="shots-by-scene">
      <div v-for="(group, sceneId) in groupedShots" :key="sceneId" class="scene-group">
        <div class="scene-label" @click="toggleScene(sceneId)">
          <span class="expand-icon">{{ expanded[sceneId] ? '▼' : '▶' }}</span>
          <span>{{ sceneLabel(sceneId) }}</span>
          <span class="shot-count">{{ group.length }} 镜</span>
        </div>
        <div v-if="expanded[sceneId]" class="scene-shots">
          <div
            v-for="shot in group"
            :key="shot.id"
            :class="['shot-card', { selected: selectedShot === shot.id }]"
            @click="$emit('select-shot', shot)"
          >
            <div class="shot-top">
              <span class="shot-type-badge">{{ shotTypeLabel(shot.shot_type) }}</span>
              <span class="shot-order">#{{ shot.order + 1 }}</span>
              <span class="shot-duration">{{ shot.duration_sec }}s</span>
              <span :class="['video-status', videoStatusClass(shot)]">
                {{ videoStatusLabel(shot) }}
              </span>
            </div>
            <div class="shot-subject">{{ shot.subject }}</div>
            <div class="shot-action">{{ shot.action }}</div>
            <div class="shot-meta">
              <span v-if="shot.camera?.type !== 'static'" class="meta-tag">
                {{ cameraLabel(shot.camera) }}
              </span>
              <span v-if="shot.lighting" class="meta-tag">💡 {{ shot.lighting }}</span>
              <span v-if="shot.mood" class="meta-tag">🎭 {{ shot.mood }}</span>
            </div>
            <div v-if="shot.video_prompt" class="shot-prompt">
              <span class="prompt-label">Prompt:</span>
              <span class="prompt-text">{{ truncate(shot.video_prompt, 100) }}</span>
            </div>
            <div class="shot-actions-row">
              <button
                class="btn-tiny ok"
                @click.stop="$emit('generate-video', shot)"
                v-if="shot.video_prompt && !shot.video_url"
              >生成视频</button>
              <button
                class="btn-tiny"
                @click.stop="$emit('play-video', shot)"
                v-if="shot.video_url"
              >▶ 播放</button>
              <button
                class="btn-tiny"
                @click.stop="$emit('edit-prompt', shot)"
              >编辑 Prompt</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'

const props = defineProps({
  shots: { type: Array, default: () => [] },
  scenes: { type: Array, default: () => [] },
  selectedShot: { type: String, default: null },
})

const emit = defineEmits(['select-shot', 'generate-video', 'generate-all', 'play-video', 'edit-prompt', 'refresh'])

const expanded = reactive({})

const groupedShots = computed(() => {
  const groups = {}
  for (const shot of props.shots) {
    const sid = shot.scene_id || 'unknown'
    if (!groups[sid]) groups[sid] = []
    groups[sid].push(shot)
  }
  // 每组按 order 排序
  for (const key of Object.keys(groups)) {
    groups[key].sort((a, b) => (a.order || 0) - (b.order || 0))
  }
  return groups
})

// 默认展开所有场景
const _initExpanded = () => {
  for (const key of Object.keys(groupedShots.value)) {
    if (expanded[key] === undefined) expanded[key] = true
  }
}
_initExpanded()

function toggleScene(id) { expanded[id] = !expanded[id] }

function sceneLabel(sceneId) {
  const sc = props.scenes.find(s => s.id === sceneId)
  return sc ? `${sc.id} ${sc.title}` : sceneId
}

const shotTypeLabels = {
  extreme_wide: '极远景', wide: '远景', medium: '中景',
  close_up: '近景', extreme_close_up: '特写', over_shoulder: '过肩', pov: '主观',
}
function shotTypeLabel(t) { return shotTypeLabels[t] || t }

function cameraLabel(cam) {
  if (!cam) return ''
  const labels = { pan: '摇', tilt: '俯仰', dolly: '推拉', tracking: '跟', crane: '升降', handheld: '手持', zoom: '变焦' }
  const dir = cam.direction || ''
  const speed = cam.speed === 'slow' ? '慢' : cam.speed === 'fast' ? '快' : ''
  return `${speed}${labels[cam.type] || cam.type}${dir ? ' ' + dir : ''}`
}

function videoStatusClass(shot) {
  if (shot.video_url) return 'done'
  if (shot.video_job_id) return 'generating'
  if (shot.video_prompt) return 'ready'
  return 'pending'
}

function videoStatusLabel(shot) {
  if (shot.video_url) return '✅'
  if (shot.video_job_id) return '⏳'
  if (shot.video_prompt) return '📝'
  return '—'
}

function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '...' : s }
</script>

<style scoped>
.shot-list { padding: 12px; }
.shot-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.shot-header h4 { margin: 0; font-size: 14px; }
.shot-actions { display: flex; gap: 6px; }
.btn-small { padding: 5px 12px; background: var(--code-bg, #111); border: 1px solid var(--border, #333); border-radius: 5px; color: var(--text, #eee); cursor: pointer; font-size: 11px; }
.btn-small.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
.btn-tiny { padding: 3px 8px; background: none; border: 1px solid var(--border, #333); border-radius: 4px; color: var(--text2, #999); cursor: pointer; font-size: 10px; }
.btn-tiny.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }

.empty-state { text-align: center; padding: 40px 20px; color: var(--text2, #666); }
.empty-state .hint { font-size: 12px; color: var(--text2, #555); }

.scene-group { margin-bottom: 8px; }
.scene-label {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px;
  background: rgba(255,255,255,.02); border-radius: 6px; cursor: pointer;
  font-size: 12px; font-weight: 600;
}
.scene-label:hover { background: rgba(255,255,255,.04); }
.expand-icon { font-size: 10px; color: var(--text2, #666); }
.shot-count { margin-left: auto; font-size: 11px; color: var(--text2, #666); font-weight: 400; }

.scene-shots { padding: 4px 0 4px 16px; }
.shot-card {
  padding: 10px; margin-bottom: 6px; background: rgba(255,255,255,.02);
  border: 1px solid var(--border, #222); border-radius: 6px; cursor: pointer;
  transition: border-color .15s;
}
.shot-card:hover { border-color: var(--gold, #e94560); }
.shot-card.selected { border-color: var(--cyan, #22d3ee); background: rgba(34,211,238,.03); }

.shot-top { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.shot-type-badge {
  font-size: 10px; padding: 1px 6px; background: rgba(168,85,247,.15);
  border-radius: 3px; color: var(--violet, #a855f7);
}
.shot-order { font-size: 11px; color: var(--text2, #666); }
.shot-duration { font-size: 10px; color: var(--text2, #555); }
.video-status { font-size: 12px; margin-left: auto; }
.video-status.done { color: var(--green, #4ade80); }
.video-status.generating { color: var(--gold, #e94560); }
.video-status.ready { color: var(--cyan, #22d3ee); }
.video-status.pending { color: var(--text2, #444); }

.shot-subject { font-size: 13px; margin-bottom: 2px; }
.shot-action { font-size: 11px; color: var(--text2, #888); margin-bottom: 4px; }
.shot-meta { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.meta-tag { font-size: 10px; padding: 1px 5px; background: rgba(255,255,255,.04); border-radius: 3px; color: var(--text2, #777); }

.shot-prompt { font-size: 10px; color: var(--text2, #666); margin-bottom: 6px; line-height: 1.4; }
.prompt-label { color: var(--violet, #a855f7); }

.shot-actions-row { display: flex; gap: 4px; }
</style>
