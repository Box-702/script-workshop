<template>
  <div class="prompt-editor" v-if="shot">
    <div class="editor-header">
      <h4>编辑视频 Prompt</h4>
      <button class="btn-ghost" @click="$emit('close')">✕</button>
    </div>

    <div class="shot-info">
      <span class="shot-badge">{{ shot.shot_type }}</span>
      <span>{{ shot.subject }}</span>
    </div>

    <div class="editor-field">
      <label>视频 Prompt（英文）</label>
      <textarea
        v-model="editedPrompt"
        class="prompt-textarea"
        rows="6"
        placeholder="A medium close-up shot with slow dolly in of..."
      />
      <div class="char-count">{{ editedPrompt.length }} 字</div>
    </div>

    <div class="prompt-hints">
      <div class="hint-title">Prompt 结构参考</div>
      <div class="hint-text">[镜头类型] + [运镜方式] of [主体] [动作] in [环境], [光线], [风格/情绪]</div>
      <div class="hint-example">
        "A medium close-up shot with slow dolly in of a young woman sitting alone
        by a rain-streaked window, soft warm interior lighting, cinematic 35mm film"
      </div>
    </div>

    <div class="editor-actions">
      <button class="btn ok" @click="save">保存</button>
      <button class="btn" @click="regenerate">让 AI 重新生成</button>
      <button class="btn-ghost" @click="$emit('close')">取消</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  shot: { type: Object, default: null },
})

const emit = defineEmits(['close', 'save', 'regenerate'])

const editedPrompt = ref('')

watch(() => props.shot, (s) => {
  editedPrompt.value = s?.video_prompt || ''
}, { immediate: true })

function save() {
  emit('save', { ...props.shot, video_prompt: editedPrompt.value })
}

function regenerate() {
  emit('regenerate', props.shot)
}
</script>

<style scoped>
.prompt-editor {
  background: var(--panel, #1a1a2e); border: 1px solid var(--border, #333);
  border-radius: 10px; padding: 16px;
}
.editor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.editor-header h4 { margin: 0; font-size: 14px; }
.btn-ghost { background: none; border: none; color: var(--text2, #999); cursor: pointer; }

.shot-info { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 13px; }
.shot-badge { font-size: 10px; padding: 2px 6px; background: rgba(168,85,247,.15); border-radius: 3px; color: var(--violet, #a855f7); }

.editor-field { margin-bottom: 12px; }
.editor-field label { display: block; font-size: 12px; color: var(--text2, #999); margin-bottom: 4px; }
.prompt-textarea {
  width: 100%; padding: 10px; background: var(--code-bg, #111); border: 1px solid var(--border, #333);
  border-radius: 6px; color: var(--text, #eee); font-size: 13px; font-family: inherit;
  resize: vertical; box-sizing: border-box; line-height: 1.5;
}
.prompt-textarea:focus { outline: none; border-color: var(--gold, #e94560); }
.char-count { text-align: right; font-size: 11px; color: var(--text2, #555); margin-top: 4px; }

.prompt-hints {
  padding: 10px; background: rgba(255,255,255,.02); border: 1px solid var(--border, #222);
  border-radius: 6px; margin-bottom: 12px;
}
.hint-title { font-size: 11px; color: var(--text2, #888); margin-bottom: 4px; }
.hint-text { font-size: 11px; color: var(--cyan, #22d3ee); margin-bottom: 6px; }
.hint-example { font-size: 10px; color: var(--text2, #666); font-style: italic; line-height: 1.4; }

.editor-actions { display: flex; gap: 8px; }
.btn {
  padding: 7px 16px; background: var(--code-bg, #111); border: 1px solid var(--border, #333);
  border-radius: 6px; color: var(--text, #eee); cursor: pointer; font-size: 12px;
}
.btn.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
</style>
