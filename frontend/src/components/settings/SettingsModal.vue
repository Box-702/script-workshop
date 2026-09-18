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
            <div class="form-row">
              <label>Provider</label>
              <select v-model="llmForm.provider" class="input">
                <option value="openai">OpenAI 兼容</option>
                <option value="deepseek">DeepSeek</option>
                <option v-for="p in llmProviders" :key="p.id" :value="p.name">{{ p.label }}</option>
              </select>
            </div>
            <div class="form-row">
              <label>API Key</label>
              <div class="key-row">
                <input
                  :type="showKey ? 'text' : 'password'"
                  v-model="llmForm.apiKey"
                  class="input"
                  placeholder="sk-..."
                />
                <button class="btn-small" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button>
                <button class="btn-small ok" @click="testLlm" :disabled="testing">
                  {{ testing ? '测试中...' : '测试连接' }}
                </button>
              </div>
            </div>
            <div class="form-row">
              <label>Base URL</label>
              <input v-model="llmForm.baseUrl" class="input" placeholder="https://api.openai.com/v1" />
            </div>
            <div class="form-row">
              <label>模型名</label>
              <input v-model="llmForm.model" class="input" placeholder="gpt-4o-mini" />
            </div>
            <div v-if="testResult" :class="['test-result', testResult.ok ? 'ok' : 'err']">
              {{ testResult.message }}
            </div>
          </div>

          <!-- 视频生成 -->
          <div v-if="tab === 'video'" class="section">
            <h4>视频生成 Provider</h4>
            <div class="provider-list">
              <div
                v-for="p in videoProviders"
                :key="p.id"
                class="provider-card"
              >
                <div class="provider-header">
                  <span class="provider-icon">{{ providerIcon(p.name) }}</span>
                  <span class="provider-name">{{ p.label }}</span>
                  <span :class="['status-dot', p.configured ? 'on' : 'off']"></span>
                  <span class="provider-price" v-if="providerPrice(p.name)">{{ providerPrice(p.name) }}</span>
                </div>
                <div class="provider-meta">
                  <span v-if="providerChinese(p.name)" class="badge-cn">中文</span>
                  <span class="badge">{{ providerDuration(p.name) }}</span>
                </div>
                <div class="provider-actions">
                  <button class="btn-small" @click="editProvider(p)">配置</button>
                  <button class="btn-small danger" @click="deleteProvider(p)" v-if="p.configured">删除</button>
                </div>
              </div>
              <div class="provider-card add" @click="showAddProvider = true">
                <span>+ 添加 Provider</span>
              </div>
            </div>

            <!-- 添加/编辑 Provider 弹窗 -->
            <div v-if="showAddProvider || editingProvider" class="sub-modal">
              <h5>{{ editingProvider ? '编辑' : '添加' }} Video Provider</h5>
              <div class="form-row">
                <label>Provider</label>
                <select v-model="providerForm.name" class="input" :disabled="!!editingProvider">
                  <option value="runway">Runway Gen-4</option>
                  <option value="kling">Kling AI (快手)</option>
                  <option value="cogvideo">CogVideoX (智谱)</option>
                  <option value="sora">Sora 2 (OpenAI)</option>
                  <option value="minimax">MiniMax 海螺</option>
                </select>
              </div>
              <div class="form-row">
                <label>API Key</label>
                <input
                  :type="showVideoKey ? 'text' : 'password'"
                  v-model="providerForm.apiKey"
                  class="input"
                  placeholder="输入 API Key"
                />
                <button class="btn-small" @click="showVideoKey = !showVideoKey">{{ showVideoKey ? '隐藏' : '显示' }}</button>
              </div>
              <div class="form-row">
                <label>Base URL（可选）</label>
                <input v-model="providerForm.baseUrl" class="input" placeholder="默认" />
              </div>
              <div class="form-actions">
                <button class="btn ok" @click="saveProvider">保存</button>
                <button class="btn-ghost" @click="cancelEdit">取消</button>
              </div>
            </div>
          </div>

          <!-- 模型偏好 -->
          <div v-if="tab === 'prefs'" class="section">
            <h4>任务模型偏好</h4>
            <div v-for="pref in preferences" :key="pref.task_type" class="pref-row">
              <span class="pref-label">{{ taskLabel(pref.task_type) }}</span>
              <span class="pref-model">{{ pref.model_name || '使用默认' }}</span>
              <button class="btn-small" @click="editPref(pref)">修改</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
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
const testing = ref(false)
const testResult = ref(null)
const llmForm = reactive({ provider: 'openai', apiKey: '', baseUrl: '', model: '' })
const llmProviders = ref([])

// ---- 视频 Provider ----
const videoProviders = ref([])
const showAddProvider = ref(false)
const editingProvider = ref(null)
const showVideoKey = ref(false)
const providerForm = reactive({ name: 'kling', apiKey: '', baseUrl: '' })

// ---- 模型偏好 ----
const preferences = ref([])

const providerIcons = { runway: 'RW', kling: 'KL', cogvideo: 'CG', sora: 'SO', minimax: 'MX' }
const providerPrices = { runway: '$0.05-0.12/s', kling: '$0.10-0.20/s', cogvideo: '按量', sora: '$0.10-0.50/s', minimax: '$0.045/s' }
const providerChinese = (n) => ['kling', 'cogvideo', 'minimax'].includes(n)
const providerIcon = (n) => providerIcons[n] || 'AI'
const providerPrice = (n) => providerPrices[n] || ''
const providerDuration = (n) => ({ runway: '10s', kling: '10s', cogvideo: '6s', sora: '20s', minimax: '10s' }[n] || '')
const taskLabels = { screenplay: '剧本生成', shot_design: '镜头设计', video_gen: '视频生成', image_gen: '图片生成', tts: '语音合成' }
const taskLabel = (t) => taskLabels[t] || t

async function loadProviders() {
  try {
    const all = await api('/providers')
    videoProviders.value = all.filter(p => p.kind === 'video')
    llmProviders.value = all.filter(p => p.kind === 'llm')
  } catch {}
}

async function loadPreferences() {
  try { preferences.value = await api('/models/preferences') } catch {}
}

async function testLlm() {
  testing.value = true
  testResult.value = null
  try {
    const res = await api('/providers/test', 'POST', { provider: llmForm.provider, api_key: llmForm.apiKey })
    testResult.value = { ok: res.ok, message: res.ok ? '连接成功' : `失败：${res.error}` }
  } catch (e) {
    testResult.value = { ok: false, message: `错误：${e.message}` }
  } finally {
    testing.value = false
  }
}

function editProvider(p) {
  editingProvider.value = p
  providerForm.name = p.name
  providerForm.apiKey = ''
  providerForm.baseUrl = p.base_url || ''
}

function cancelEdit() {
  showAddProvider.value = false
  editingProvider.value = null
  providerForm.apiKey = ''
  providerForm.baseUrl = ''
}

async function saveProvider() {
  try {
    if (editingProvider.value) {
      await api(`/providers/${editingProvider.value.id}`, 'PATCH', {
        api_key: providerForm.apiKey || undefined,
        base_url: providerForm.baseUrl || undefined,
      })
    } else {
      const labelMap = { runway: 'Runway Gen-4', kling: 'Kling AI', cogvideo: 'CogVideoX', sora: 'Sora 2', minimax: 'MiniMax 海螺' }
      await api('/providers', 'POST', {
        kind: 'video',
        name: providerForm.name,
        label: labelMap[providerForm.name] || providerForm.name,
        api_key: providerForm.apiKey,
        base_url: providerForm.baseUrl,
      })
    }
    cancelEdit()
    await loadProviders()
  } catch (e) {
    alert(`保存失败：${e.message}`)
  }
}

async function deleteProvider(p) {
  if (!confirm(`确定删除 ${p.label}？`)) return
  try {
    await api(`/providers/${p.id}`, 'DELETE')
    await loadProviders()
  } catch (e) {
    alert(`删除失败：${e.message}`)
  }
}

function editPref(pref) {
  // TODO: 打开偏好编辑对话框
}

watch(() => props.open, (v) => {
  if (v) {
    loadProviders()
    loadPreferences()
  }
})

onMounted(() => {
  if (props.open) {
    loadProviders()
    loadPreferences()
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
