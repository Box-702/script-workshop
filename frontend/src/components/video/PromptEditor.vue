<template>
  <div class="prompt-editor" v-if="shot">
    <div class="editor-header">
      <div>
        <div class="eyebrow">HUMAN REVIEW</div>
        <h4>审阅镜头 Prompt</h4>
      </div>
      <button class="btn-ghost" aria-label="关闭 Prompt 审阅" @click="$emit('close')">关闭</button>
    </div>

    <div class="shot-info">
      <span class="shot-badge">{{ shot.shot_type }}</span>
      <span class="shot-title">{{ shot.subject }}</span>
      <span class="review-status" :class="statusClass">{{ statusLabel }}</span>
    </div>

    <div class="editor-field">
      <label for="prompt-review-text">视频 Prompt</label>
      <textarea
        id="prompt-review-text"
        v-model="editedPrompt"
        class="prompt-textarea"
        rows="9"
        placeholder="输入这一个镜头最终要交给视频模型的描述"
      />
      <div class="field-foot">
        <span>这是当前镜头的最终出片指令，批准后才会进入生成队列。</span>
        <span class="char-count">{{ editedPrompt.length }} 字</span>
      </div>
    </div>

    <div class="editor-field">
      <label for="prompt-review-note">审阅备注 <span>可选</span></label>
      <textarea
        id="prompt-review-note"
        v-model="note"
        class="note-textarea"
        rows="2"
        placeholder="记录为什么这样改，方便回看版本"
      />
    </div>

    <div class="editor-actions">
      <button class="btn-ghost" @click="$emit('close')">取消</button>
      <button class="btn" :disabled="!editedPrompt.trim()" @click="review('needs_revision')">标记需修改</button>
      <button class="btn" :disabled="!editedPrompt.trim()" @click="review('save')">保存草稿</button>
      <button class="btn ok" :disabled="!editedPrompt.trim()" @click="review('approve')">
        批准并解锁出片
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  shot: { type: Object, default: null },
})

const emit = defineEmits(['close', 'review'])

const editedPrompt = ref('')
const note = ref('')

watch(() => props.shot, (s) => {
  editedPrompt.value = s?.video_prompt || ''
  note.value = s?.prompt_review_note || ''
}, { immediate: true })

const statusLabel = computed(() => ({
  approved: '已批准',
  needs_review: '待审阅',
  needs_revision: '需修改',
}[props.shot?.prompt_status] || '待审阅'))

const statusClass = computed(() => props.shot?.prompt_status || 'needs_review')

function review(decision) {
  emit('review', {
    ...props.shot,
    video_prompt: editedPrompt.value.trim(),
    prompt_review_note: note.value.trim(),
    decision,
  })
}
</script>

<style scoped>
.prompt-editor {
  background: var(--panel2); border: 1px solid var(--line);
  border-radius: 10px; padding: 16px;
}
.editor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.editor-header h4 { margin: 3px 0 0; font-size: 15px; }
.eyebrow { color: var(--gold); font: 700 9px/1 var(--mono); letter-spacing: .12em; }
.btn-ghost { background: transparent; border: 1px solid var(--line); color: var(--muted); cursor: pointer; }

.shot-info { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; font-size: 13px; }
.shot-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shot-badge { font-size: 10px; padding: 2px 6px; background: var(--violet-soft); border-radius: 3px; color: var(--violet); }
.review-status { margin-left: auto; font-size: 11px; white-space: nowrap; }
.review-status.approved { color: var(--ok); }
.review-status.needs_review { color: var(--warn); }
.review-status.needs_revision { color: var(--bad); }

.editor-field { margin-bottom: 12px; }
.editor-field label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 5px; }
.editor-field label span { color: var(--dim); font-size: 11px; }
.prompt-textarea {
  width: 100%; padding: 10px; background: var(--code-bg); border: 1px solid var(--line);
  border-radius: 6px; color: var(--text, #eee); font-size: 13px; font-family: inherit;
  resize: vertical; box-sizing: border-box; line-height: 1.5;
}
.prompt-textarea:focus { outline: none; border-color: var(--gold); }
.note-textarea {
  width: 100%; padding: 8px 10px; background: var(--code-bg); border: 1px solid var(--line);
  border-radius: 6px; color: var(--ink); font-size: 12px; font-family: inherit;
  resize: vertical; box-sizing: border-box; line-height: 1.45;
}
.note-textarea:focus { outline: none; border-color: var(--gold); }
.field-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 5px; color: var(--dim); font-size: 10.5px; line-height: 1.4; }
.char-count { flex: none; font-variant-numeric: tabular-nums; }
.editor-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.btn {
  padding: 7px 12px; background: var(--code-bg); border: 1px solid var(--line);
  border-radius: 6px; color: var(--text, #eee); cursor: pointer; font-size: 12px;
}
.btn.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
.btn:disabled { opacity: .45; cursor: not-allowed; }

@media (max-width: 620px) {
  .field-foot { display: block; }
  .char-count { display: block; margin-top: 3px; }
  .editor-actions { justify-content: stretch; }
  .editor-actions > * { flex: 1; }
}
</style>
