<template>
  <Teleport to="body">
    <div v-if="open" class="modal-mask" @click.self="$emit('close')">
      <div class="modal-box">
        <div class="modal-header">
          <h3>⚙️ 模型与 API 设置</h3>
          <button class="btn-ghost" @click="$emit('close')">✕</button>
        </div>

        <div class="modal-tabs">
          <button
            v-for="t in tabs"
            :key="t.key"
            :class="['tab', { active: tab === t.key }]"
            @click="tab = t.key"
          >{{ t.label }}</button>
        </div>

        <div class="modal-body">
          <!-- 对话模型 -->
          <div v-if="tab === 'llm'" class="section">
            <h4>对话模型（编剧/导演使用）</h4>
            <div class="active-line">
              当前生效：<strong>{{ activeModel.provider }}</strong>
              <template v-if="activeModel.name"> · {{ activeModel.name }}</template>
              <span class="active-src">{{ activeSourceLabel }}</span>
            </div>

            <div class="llm-list">
              <div
                v-for="p in llmProviders"
                :key="p.id"
                :class="['llm-card', { active: chatPref?.provider_id === p.id }]"
              >
                <div class="llm-main">
                  <span class="llm-name">{{ p.label }}</span>
                  <span class="llm-meta">{{ p.name }} · {{ p.config?.model || '未填模型名' }}</span>
                </div>
                <span v-if="chatPref?.provider_id === p.id" class="using-badge">使用中</span>
                <div class="llm-actions">
                  <button
                    v-if="chatPref?.provider_id !== p.id"
                    class="btn-small ok"
                    :disabled="!p.configured"
                    @click="setAsDefault(p)"
                  >设为默认</button>
                  <button class="btn-small" @click="testProvider(p)" :disabled="p.testing">
                    {{ p.testing ? '测试中…' : '测试' }}
                  </button>
                  <button class="btn-small" @click="editLlm(p)">编辑</button>
                  <button class="btn-small danger" @click="deleteLlm(p)">删除</button>
                </div>
                <div v-if="p.testResult" :class="['test-result', p.testResult.ok ? 'ok' : 'err']">
                  {{ p.testResult.message }}
                </div>
              </div>
              <div class="llm-card add" @click="openAddLlm()">
                <span>＋ 添加自定义模型</span>
              </div>
            </div>

            <button class="follow-env" @click="followEnv">
              恢复 .env 默认（当前：{{ envModelLabel }}）
            </button>

            <!-- 添加/编辑自定义模型 -->
            <div v-if="showAddLlm || editingLlmRow" class="sub-modal">
              <h5>{{ editingLlmRow ? '编辑模型' : '添加自定义模型' }}</h5>
              <div class="form-row">
                <label>厂商预设</label>
                <select v-model="llmForm.preset" class="input" :disabled="!!editingLlmRow" @change="applyPreset()">
                  <option value="deepseek">DeepSeek</option>
                  <option value="zhipu">智谱 (BigModel)</option>
                  <option value="openai">OpenAI 兼容</option>
                  <option value="custom">自定义</option>
                </select>
              </div>
              <div v-if="llmForm.preset === 'custom'" class="form-row">
                <label>名称（唯一标识）</label>
                <input v-model.trim="llmForm.name" class="input" placeholder="my-provider" />
              </div>
              <div class="form-row">
                <label>显示名</label>
                <input v-model.trim="llmForm.label" class="input" placeholder="我的模型" />
              </div>
              <div class="form-row">
                <label>Base URL</label>
                <input v-model.trim="llmForm.baseUrl" class="input" placeholder="https://api.deepseek.com/v1" />
              </div>
              <div class="form-row">
                <label>模型名</label>
                <input v-model.trim="llmForm.model" class="input" placeholder="deepseek-flash" />
              </div>
              <div class="form-row">
                <label>API Key</label>
                <div class="key-row">
                  <input
                    :type="showKey ? 'text' : 'password'"
                    v-model="llmForm.apiKey"
                    class="input"
                    :placeholder="editingLlmRow ? '留空 = 保持不变' : 'sk-...'"
                  />
                  <button class="btn-small" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button>
                </div>
              </div>
              <div v-if="llmFormError" class="test-result err">{{ llmFormError }}</div>
              <div class="form-actions">
                <button class="btn ok" @click="saveLlm" :disabled="savingLlm">
                  {{ savingLlm ? '保存中…' : '保存' }}
                </button>
                <button class="btn-ghost" @click="closeLlmForm">取消</button>
              </div>
            </div>
          </div>

          <!-- 视频生成 -->
          <div v-if="tab === 'video'" class="section">
            <h4>视频生成（MiniMax 海螺）</h4>
            <div class="active-line">
              <template v-if="minimaxRow">
                <span :class="['status-dot', minimaxRow.configured ? 'on' : 'off']"></span>
                已配置 <strong>MiniMax</strong>
                · 模型 <strong>{{ minimaxModelLabel }}</strong>
                <span class="active-src">用自己的 Key，费用直接走你的 MiniMax 账户</span>
              </template>
              <template v-else>
                填入你的 MiniMax API Key 后即可生成视频
              </template>
            </div>
            <div class="form-row">
              <label>API Key</label>
              <div class="key-row">
                <input
                  :type="showVideoKey ? 'text' : 'password'"
                  v-model="videoForm.apiKey"
                  class="input"
                  :placeholder="minimaxRow?.configured ? '留空 = 保持不变' : 'MiniMax 开放平台 API Key'"
                />
                <button class="btn-small" @click="showVideoKey = !showVideoKey">{{ showVideoKey ? '隐藏' : '显示' }}</button>
              </div>
            </div>
            <div class="form-row">
              <label>模型</label>
              <input v-model.trim="videoForm.model" class="input" placeholder="MiniMax-H3" />
            </div>
            <div class="form-row">
              <label>Base URL（可选）</label>
              <input v-model.trim="videoForm.baseUrl" class="input" placeholder="默认 https://api.minimax.cn" />
            </div>
            <p class="pref-hint">
              海外账户填 https://api.minimaxi.com；Key 与模型只存在本机数据库，不经过任何第三方。
            </p>
            <div class="form-actions">
              <button class="btn ok" @click="saveMinimax">保存</button>
            </div>
          </div>

          <!-- 模型偏好 -->
          <div v-if="tab === 'prefs'" class="section">
            <h4>任务模型偏好</h4>
            <div class="active-line">
              对话任务：<strong>{{ chatPrefLabel }}</strong>
              <span class="active-src">{{ chatPref ? '界面指定' : '跟随 .env' }}</span>
            </div>
            <p class="pref-hint">
              在「对话模型」列表里点「设为默认」即可切换；切回 .env 默认用「恢复 .env 默认」。
            </p>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { api } from '../../api.js'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['close'])

const tab = ref('llm')
const tabs = [
  { key: 'llm', label: '对话模型' },
  { key: 'video', label: '视频生成' },
  { key: 'prefs', label: '模型偏好' },
]

// ---- 对话模型 ----
const showKey = ref(false)
const llmForm = reactive({ provider: 'openai', apiKey: '', baseUrl: '', model: '' })
const llmProviders = ref([])
const activeModel = ref({ provider: '-', name: '' })
const activeSource = ref('env')
const chatPref = ref(null)          // task_type=chat 的偏好（含 provider_id）
const showAddLlm = ref(false)
const editingLlmRow = ref(null)
const llmFormError = ref('')
const savingLlm = ref(false)

const PRESETS = {
  deepseek: { label: 'DeepSeek', name: 'deepseek', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-flash' },
  zhipu: { label: '智谱 (BigModel)', name: 'zhipu', baseUrl: 'https://open.bigmodel.cn/api/paas/v4/', model: 'GLM-5.3-Flash' },
  openai: { label: 'OpenAI 兼容', name: 'openai', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  custom: { label: '', name: '', baseUrl: '', model: '' },
}
const PRESET_LABELS = { deepseek: 'DeepSeek', zhipu: '智谱', openai: 'OpenAI 兼容' }

const activeSourceLabel = computed(() =>
  ({ db: '界面指定', env: '.env 配置', default: '未配置' }[activeSource.value] || activeSource.value))
const chatPrefLabel = computed(() => {
  if (!chatPref.value) return '跟随 .env 默认'
  const p = llmProviders.value.find(x => x.id === chatPref.value.provider_id)
  const model = chatPref.value.model_name || p?.config?.model || ''
  return (p?.label || chatPref.value.provider_id) + (model ? ' · ' + model : '')
})
const envModelLabel = computed(() => {
  if (activeSource.value !== 'env') return '见 .env'
  return activeModel.value.provider + (activeModel.value.name ? ' · ' + activeModel.value.name : '')
})

async function loadModelInfo() {
  try {
    const d = await api('/status')
    activeModel.value = d.model || { provider: '-', name: '' }
    activeSource.value = d.model?.source || 'env'
  } catch { /* 保持占位 */ }
}

async function loadChatPref() {
  try {
    const prefs = await api('/models/preferences')
    chatPref.value = prefs.find(x => x.task_type === 'chat' && x.provider_id) || null
  } catch { chatPref.value = null }
}

async function setAsDefault(p) {
  try {
    await api('/models/preferences', 'PUT', {
      task_type: 'chat',
      provider_id: p.id,
      model_name: p.config?.model || '',
      is_default: true,
    })
    await Promise.all([loadChatPref(), loadModelInfo(), loadProviders()])
  } catch (e) {
    alert('设置失败：' + e.message)
  }
}

async function followEnv() {
  try {
    // provider_id 置空 = 清除界面指定，回落到 .env 链
    await api('/models/preferences', 'PUT', {
      task_type: 'chat', provider_id: null, model_name: '', is_default: true,
    })
    await Promise.all([loadChatPref(), loadModelInfo()])
  } catch (e) {
    alert('恢复失败：' + e.message)
  }
}

function applyPreset() {
  const pre = PRESETS[llmForm.preset]
  if (!pre || editingLlmRow.value) return
  if (!llmForm.label) llmForm.label = pre.label
  llmForm.baseUrl = pre.baseUrl
  llmForm.model = pre.model
}

function openAddLlm() {
  llmForm.preset = 'deepseek'
  llmForm.name = ''
  llmForm.label = ''
  llmForm.baseUrl = PRESETS.deepseek.baseUrl
  llmForm.model = PRESETS.deepseek.model
  llmForm.apiKey = ''
  llmFormError.value = ''
  showAddLlm.value = true
}

function editLlm(p) {
  editingLlmRow.value = p
  llmForm.preset = PRESET_LABELS[p.name] ? p.name : 'custom'
  llmForm.name = p.name
  llmForm.label = p.label
  llmForm.baseUrl = p.base_url || ''
  llmForm.model = p.config?.model || ''
  llmForm.apiKey = ''
  llmFormError.value = ''
}

function closeLlmForm() {
  showAddLlm.value = false
  editingLlmRow.value = null
  llmForm.apiKey = ''
  llmFormError.value = ''
}

async function saveLlm() {
  const model = llmForm.model.trim()
  const baseUrl = llmForm.baseUrl.trim()
  if (!model) { llmFormError.value = '模型名必填'; return }
  if (!baseUrl) { llmFormError.value = 'Base URL 必填'; return }
  if (!editingLlmRow.value && llmForm.preset === 'custom' && !llmForm.name.trim()) {
    llmFormError.value = '自定义厂商需要名称'; return
  }
  if (!editingLlmRow.value && !llmForm.apiKey.trim()) {
    llmFormError.value = 'API Key 必填'; return
  }
  savingLlm.value = true
  llmFormError.value = ''
  try {
    if (editingLlmRow.value) {
      await api('/providers/' + editingLlmRow.value.id, 'PATCH', {
        label: llmForm.label.trim(),
        base_url: baseUrl,
        config: { model },
        api_key: llmForm.apiKey.trim() || undefined,
      })
    } else {
      const preset = PRESETS[llmForm.preset]
      const name = llmForm.preset === 'custom' ? llmForm.name.trim() : preset.name
      const label = llmForm.label.trim() || preset.label || name
      await api('/providers', 'POST', {
        kind: 'llm', name, label, base_url: baseUrl,
        api_key: llmForm.apiKey.trim(), config: { model }, enabled: true,
      })
    }
    closeLlmForm()
    await Promise.all([loadProviders(), loadModelInfo()])
  } catch (e) {
    llmFormError.value = '保存失败：' + e.message
  } finally {
    savingLlm.value = false
  }
}

async function testProvider(p) {
  p.testing = true
  try {
    const res = await api('/providers/' + p.id + '/test', 'POST')
    p.testResult = { ok: res.ok, message: res.ok ? '连接成功（' + (res.label || res.provider) + '）' : '失败：' + res.error }
  } catch (e) {
    p.testResult = { ok: false, message: '错误：' + e.message }
  } finally {
    p.testing = false
  }
}

async function deleteLlm(p) {
  if (!confirm('确定删除 ' + p.label + '？')) return
  try {
    await api('/providers/' + p.id, 'DELETE')
    if (chatPref.value?.provider_id === p.id) chatPref.value = null
    await Promise.all([loadProviders(), loadModelInfo()])
  } catch (e) {
    alert('删除失败：' + e.message)
  }
}

// ---- 视频 Provider（MiniMax，用户自带 Key 与模型）----
const videoProviders = ref([])
const showVideoKey = ref(false)
const videoForm = reactive({ apiKey: '', model: '', baseUrl: '' })
const minimaxRow = computed(() => videoProviders.value.find(p => p.name === 'minimax'))
const minimaxModelLabel = computed(() => minimaxRow.value?.config?.model || 'MiniMax-H3')

// ---- 模型偏好 ----

const taskLabels = { screenplay: '剧本生成', shot_design: '镜头设计', video_gen: '视频生成', image_gen: '图片生成', tts: '语音合成' }
const taskLabel = (t) => taskLabels[t] || t

async function loadProviders() {
  try {
    const all = await api('/providers')
    videoProviders.value = all.filter(p => p.kind === 'video')
    llmProviders.value = all.filter(p => p.kind === 'llm').map(p => ({ ...p, testing: false, testResult: null }))
  } catch {}
  syncVideoForm()
  if (showAddLlm.value && !editingLlmRow.value && !llmForm.label) applyPreset()
}

/** 用已保存的 MiniMax 配置回填表单（Key 永远留空，表示「保持不变」）。 */
function syncVideoForm() {
  videoForm.apiKey = ''
  videoForm.model = minimaxRow.value?.config?.model || 'MiniMax-H3'
  videoForm.baseUrl = minimaxRow.value?.base_url || ''
}

async function saveMinimax() {
  const key = videoForm.apiKey.trim()
  if (!minimaxRow.value && !key) {
    alert('请先填入 MiniMax API Key')
    return
  }
  try {
    const config = videoForm.model ? { model: videoForm.model } : {}
    if (minimaxRow.value) {
      await api(`/providers/${minimaxRow.value.id}`, 'PATCH', {
        api_key: key || undefined,
        base_url: videoForm.baseUrl,
        config,
      })
    } else {
      await api('/providers', 'POST', {
        kind: 'video',
        name: 'minimax',
        label: 'MiniMax 海螺',
        api_key: key,
        base_url: videoForm.baseUrl,
        config,
      })
    }
    await loadProviders()
  } catch (e) {
    alert(`保存失败：${e.message}`)
  }
}

watch(() => props.open, (v) => {
  if (v) {
    loadProviders()
    loadModelInfo()
    loadChatPref()
  }
})

onMounted(() => {
  if (props.open) {
    loadProviders()
    loadModelInfo()
    loadChatPref()
  }
})
</script>

<style scoped>
.modal-mask {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center;
}
.modal-box {
  background: var(--panel, #1a1a2e); border: 1px solid var(--border, #333);
  border-radius: 12px; width: 640px; max-height: 80vh; overflow-y: auto;
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid var(--border, #333);
}
.modal-header h3 { margin: 0; font-size: 16px; }
.modal-tabs {
  display: flex; gap: 0; border-bottom: 1px solid var(--border, #333);
}
.tab {
  flex: 1; padding: 10px; background: none; border: none; color: var(--text2, #999);
  cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent;
}
.tab.active { color: var(--gold, #e94560); border-bottom-color: var(--gold, #e94560); }
.modal-body { padding: 20px; }
.active-line {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 8px 12px; margin-bottom: 14px;
  border: 1px solid var(--border, #333); border-radius: 8px;
  background: var(--code-bg, #111); color: var(--text2, #999); font-size: 12px;
}
.active-line strong { color: var(--text, #eee); }
.active-src {
  margin-left: auto; font-size: 10px; padding: 1px 6px;
  border: 1px solid var(--border, #333); border-radius: 999px; color: var(--text2, #999);
}
.llm-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.llm-card {
  border: 1px solid var(--border, #333); border-radius: 9px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 6px;
}
.llm-card.active { border-color: var(--gold, #e94560); }
.llm-card.add {
  align-items: center; justify-content: center; cursor: pointer;
  border-style: dashed; color: var(--text2, #999); font-size: 12.5px; padding: 12px;
  transition: color 150ms, border-color 150ms;
}
.llm-card.add:hover { color: var(--gold, #e94560); border-color: var(--gold, #e94560); }
.llm-main { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.llm-name { font-size: 13px; font-weight: 600; color: var(--text, #eee); }
.llm-meta { font-size: 11px; color: var(--text2, #999); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.using-badge {
  align-self: flex-start; font-size: 10px; padding: 1px 7px; border-radius: 999px;
  color: var(--gold, #e94560); border: 1px solid var(--gold, #e94560);
}
.llm-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.follow-env {
  width: 100%; padding: 7px; border: 1px dashed var(--border, #333); border-radius: 8px;
  background: transparent; color: var(--text2, #999); font-size: 11.5px; cursor: pointer;
}
.follow-env:hover { color: var(--text, #eee); border-color: var(--text2, #999); }
.pref-hint { font-size: 12px; color: var(--text2, #999); line-height: 1.6; }
.sub-modal h5 { margin: 0 0 12px; font-size: 13px; color: var(--text, #eee); }
.section h4 { margin: 0 0 16px; font-size: 14px; color: var(--text, #eee); }
.form-row { margin-bottom: 12px; }
.form-row label { display: block; font-size: 12px; color: var(--text2, #999); margin-bottom: 4px; }
.input {
  width: 100%; padding: 8px 12px; background: var(--code-bg, #111); border: 1px solid var(--border, #333);
  border-radius: 6px; color: var(--text, #eee); font-size: 13px; box-sizing: border-box;
}
.key-row { display: flex; gap: 8px; }
.key-row .input { flex: 1; }
.btn-small {
  padding: 6px 12px; background: var(--code-bg, #111); border: 1px solid var(--border, #333);
  border-radius: 6px; color: var(--text, #eee); cursor: pointer; font-size: 12px; white-space: nowrap;
}
.btn-small.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
.btn-small.danger { border-color: var(--red, #f87171); color: var(--red, #f87171); }
.btn-small:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost {
  background: none; border: none; color: var(--text2, #999); cursor: pointer; font-size: 14px;
}
.btn { padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 13px; border: 1px solid var(--border, #333); background: var(--code-bg, #111); color: var(--text, #eee); }
.btn.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
.test-result {
  margin-top: 8px; padding: 8px 12px; border-radius: 6px; font-size: 12px;
}
.test-result.ok { background: rgba(74,222,128,.1); color: var(--green, #4ade80); }
.test-result.err { background: rgba(248,113,113,.1); color: var(--red, #f87171); }

.provider-list { display: flex; flex-direction: column; gap: 8px; }
.provider-card {
  padding: 12px; background: var(--code-bg, #111); border: 1px solid var(--border, #333);
  border-radius: 8px; display: flex; flex-direction: column; gap: 6px;
}
.provider-card.add {
  border-style: dashed; cursor: pointer; text-align: center; color: var(--text2, #999);
  padding: 20px;
}
.provider-card.add:hover { border-color: var(--gold); color: var(--gold); }
.provider-header { display: flex; align-items: center; gap: 8px; }
.provider-icon { font-size: 18px; }
.provider-name { font-weight: 600; font-size: 14px; flex: 1; }
.provider-price { font-size: 11px; color: var(--text2, #999); }
.provider-meta { display: flex; gap: 6px; }
.badge {
  font-size: 10px; padding: 2px 6px; background: rgba(255,255,255,.05);
  border-radius: 4px; color: var(--text2, #999);
}
.badge-cn { font-size: 10px; padding: 2px 6px; background: color-mix(in oklch, var(--gold) 10%, transparent); border-radius: 4px; color: var(--gold); }
.provider-actions { display: flex; gap: 6px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.on { background: var(--green, #4ade80); }
.status-dot.off { background: var(--text2, #555); }

.sub-modal {
  margin-top: 16px; padding: 16px; background: rgba(255,255,255,.03);
  border: 1px solid var(--border, #333); border-radius: 8px;
}
.sub-modal h5 { margin: 0 0 12px; font-size: 13px; }
.form-actions { display: flex; gap: 8px; margin-top: 12px; }

.pref-row {
  display: flex; align-items: center; gap: 12px; padding: 8px 0;
  border-bottom: 1px solid var(--border, #222);
}
.pref-label { flex: 0 0 100px; font-size: 13px; }
.pref-model { flex: 1; font-size: 13px; color: var(--text2, #999); }
</style>
