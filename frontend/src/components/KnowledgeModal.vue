<script setup>
// =====================================================================
// KnowledgeModal.vue —— 记忆/知识库可视化模态窗
//
// 展示 Agent 记住的所有知识（同类走向、写作手法、作者风格），
// 不占用右栏位置，从顶栏按钮或命令面板打开。
// =====================================================================

import { ref, watch } from 'vue'
import { store, loadKnowledge, KIND_NAME, notify } from '../stores/app'

const open = ref(false)

function showModal() {
  open.value = true
  loadKnowledge()
}
function hideModal() { open.value = false }

// ESC 关闭
function onKeydown(e) { if (e.key === 'Escape') hideModal() }

// 暴露给父组件
defineExpose({ showModal, hideModal })
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-overlay" role="dialog" aria-modal="true" aria-label="Agent 记忆库" @mousedown.self="hideModal" @keydown="onKeydown">
        <div class="modal">
          <div class="modal-head">
            <h3>🧠 Agent 记忆库</h3>
            <button class="ghost small" aria-label="关闭" @click="hideModal">✕</button>
          </div>
          <div class="modal-body">
            <div v-if="!store.knowledge.length" class="empty">
              <p>还没有记忆数据</p>
              <p class="empty-sub">在对话中说「记住：…」会让 Agent 记住你的偏好</p>
            </div>
            <template v-for="g in store.knowledge" :key="g.kind">
              <div class="kind-section">
                <div class="kind-head">
                  <span class="kind-icon">
                    {{ g.kind === 'plot_direction' ? '📈' : g.kind === 'technique' ? '🔧' : '✍️' }}
                  </span>
                  <span class="kind-name">{{ KIND_NAME[g.kind] || g.kind }}</span>
                  <span class="kind-count">{{ g.docs.length }} 条</span>
                </div>
                <div v-for="(d, i) in g.docs" :key="i" class="doc-card">
                  <div class="doc-text">{{ d.text }}</div>
                  <div v-if="d.source" class="doc-source">来源：{{ d.source }}</div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; z-index: 9500;
  background: oklch(0 0 0 / 0.5); backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
}
.modal {
  width: min(640px, 90vw); max-height: 80vh;
  background: var(--panel); border: 1px solid var(--line-strong);
  border-radius: 16px; box-shadow: 0 24px 80px oklch(0 0 0 / 0.5);
  display: flex; flex-direction: column; overflow: hidden;
}
.modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--line);
}
.modal-head h3 { margin: 0; font-size: 15px; font-weight: 700; color: var(--ink); }
.modal-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.empty { color: var(--dim); font-size: 13px; text-align: center; padding: 32px 16px; }
.empty p { margin: 4px 0; }
.empty-sub { font-size: 12px; }

.kind-section { margin-bottom: 20px; }
.kind-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.kind-icon { font-size: 16px; }
.kind-name { font-size: 13px; font-weight: 600; color: var(--ink); }
.kind-count { font-size: 11px; color: var(--dim); background: color-mix(in oklch, var(--ink) 6%, transparent); border-radius: 999px; padding: 0 7px; }

.doc-card {
  background: color-mix(in oklch, var(--ink) 3%, var(--panel));
  border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 14px; margin-bottom: 8px;
  transition: border-color 200ms var(--ease);
}
.doc-card:hover { border-color: var(--line-strong); }
.doc-text { font-size: 13px; color: var(--ink); line-height: 1.6; }
.doc-source { font-size: 11px; color: var(--dim); margin-top: 4px; }

/* 入场/退场动画 */
.modal-enter-active { transition: opacity 200ms var(--ease); }
.modal-leave-active { transition: opacity 150ms ease-in; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active .modal { animation: modal-pop 300ms var(--ease-bounce) both; }
@keyframes modal-pop {
  from { transform: scale(0.92) translateY(8px); opacity: 0; }
  to { transform: scale(1) translateY(0); opacity: 1; }
}
</style>
