<template>
  <div class="plugin-manager">
    <div class="pm-header">
      <h4>🧩 插件管理</h4>
      <button class="btn-small" @click="loadPlugins">刷新</button>
    </div>

    <!-- 插件列表 -->
    <div class="pm-list">
      <div
        v-for="p in plugins"
        :key="p.name"
        :class="['pm-card', { disabled: !p.enabled, error: p.error }]"
      >
        <div class="pm-card-header">
          <span class="pm-icon">{{ p.type === 'agent' ? '🤖' : p.type === 'skill' ? '⚡' : '🔧' }}</span>
          <span class="pm-name">{{ p.name }}</span>
          <span class="pm-version">v{{ p.version }}</span>
          <span class="pm-toggle">
            <button
              :class="['toggle-btn', { on: p.enabled }]"
              @click="togglePlugin(p)"
            >{{ p.enabled ? '已启用' : '已禁用' }}</button>
          </span>
        </div>
        <div class="pm-desc">{{ p.description }}</div>
        <div class="pm-meta">
          <span class="pm-stat" v-if="p.tool_count">🔧 {{ p.tool_count }} 个工具</span>
          <span class="pm-stat" v-if="p.agent_count">🤖 {{ p.agent_count }} 个 Agent</span>
          <span class="pm-stat" v-if="p.mcp">📡 MCP Server</span>
          <span class="pm-error" v-if="p.error">❌ {{ p.error }}</span>
        </div>
        <!-- 工具详情 -->
        <div class="pm-tools" v-if="p.tools && p.tools.length">
          <div class="pm-tools-title">提供的工具：</div>
          <div v-for="t in p.tools" :key="t.name" class="pm-tool-item">
            <span class="tool-name">{{ t.name }}</span>
            <span class="tool-desc">{{ t.description }}</span>
          </div>
        </div>
        <div class="pm-actions">
          <button class="btn-tiny" @click="reloadPlugin(p)" :disabled="!p.enabled">重载</button>
          <button class="btn-tiny danger" @click="uninstallPlugin(p)">卸载</button>
        </div>
      </div>

      <div v-if="!plugins.length" class="pm-empty">
        还没有安装任何插件
      </div>
    </div>

    <!-- 安装插件 -->
    <div class="pm-install">
      <h5>安装新插件</h5>
      <div class="install-row">
        <input
          v-model="installPath"
          class="input"
          placeholder="插件目录路径（如 C:\Users\me\my-plugin）"
        />
        <button class="btn-small ok" @click="doInstall" :disabled="!installPath">安装</button>
      </div>
      <div class="install-hint">
        插件目录需包含 <code>plugin.yaml</code> 清单文件。详见文档。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../../api.js'

const plugins = ref([])
const installPath = ref('')

async function loadPlugins() {
  try {
    plugins.value = await api('/plugins')
  } catch {
    plugins.value = []
  }
}

async function togglePlugin(p) {
  const action = p.enabled ? 'disable' : 'enable'
  try {
    await api(`/plugins/${p.name}/${action}`, 'POST')
    p.enabled = !p.enabled
  } catch (e) {
    alert(`操作失败：${e.message}`)
  }
}

async function reloadPlugin(p) {
  try {
    await api(`/plugins/${p.name}/reload`, 'POST')
    await loadPlugins()
  } catch (e) {
    alert(`重载失败：${e.message}`)
  }
}

async function uninstallPlugin(p) {
  if (!confirm(`确定卸载插件「${p.name}」？`)) return
  try {
    await api(`/plugins/${p.name}`, 'DELETE')
    await loadPlugins()
  } catch (e) {
    alert(`卸载失败：${e.message}`)
  }
}

async function doInstall() {
  if (!installPath.value.trim()) return
  try {
    await api('/plugins/install', 'POST', { path: installPath.value.trim() })
    installPath.value = ''
    await loadPlugins()
  } catch (e) {
    alert(`安装失败：${e.message}`)
  }
}

onMounted(loadPlugins)
</script>

<style scoped>
.plugin-manager { padding: 0; }
.pm-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.pm-header h4 { margin: 0; font-size: 15px; }
.btn-small {
  padding: 5px 12px; border: 1px solid var(--border, #333); border-radius: 5px;
  background: none; color: var(--text, #eee); cursor: pointer; font-size: 11px;
}
.btn-small.ok { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
.btn-small:disabled { opacity: .4; cursor: not-allowed; }

.pm-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
.pm-card {
  padding: 12px; background: rgba(255,255,255,.02); border: 1px solid var(--border, #222);
  border-radius: 8px;
}
.pm-card.disabled { opacity: .5; }
.pm-card.error { border-color: rgba(248,113,113,.3); }
.pm-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.pm-icon { font-size: 16px; }
.pm-name { font-weight: 600; font-size: 13px; flex: 1; }
.pm-version { font-size: 10px; color: var(--text2, #666); }
.toggle-btn {
  padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border, #333);
  background: none; color: var(--text2, #666); cursor: pointer; font-size: 10px;
}
.toggle-btn.on { border-color: var(--green, #4ade80); color: var(--green, #4ade80); }
.pm-desc { font-size: 12px; color: var(--text2, #888); margin-bottom: 6px; }
.pm-meta { display: flex; gap: 10px; margin-bottom: 6px; }
.pm-stat { font-size: 11px; color: var(--text2, #666); }
.pm-error { font-size: 11px; color: var(--red, #f87171); }
.pm-tools { margin-bottom: 6px; }
.pm-tools-title { font-size: 11px; color: var(--text2, #666); margin-bottom: 4px; }
.pm-tool-item { padding: 2px 0; font-size: 11px; }
.tool-name { color: var(--cyan, #22d3ee); margin-right: 6px; }
.tool-desc { color: var(--text2, #888); }
.pm-actions { display: flex; gap: 6px; }
.btn-tiny {
  padding: 2px 8px; border: 1px solid var(--border, #333); border-radius: 4px;
  background: none; color: var(--text2, #999); cursor: pointer; font-size: 10px;
}
.btn-tiny.danger { border-color: rgba(248,113,113,.3); color: var(--red, #f87171); }
.btn-tiny:disabled { opacity: .4; cursor: not-allowed; }

.pm-empty { padding: 20px; text-align: center; color: var(--text2, #555); font-size: 12px; }

.pm-install { }
.pm-install h5 { margin: 0 0 8px; font-size: 13px; }
.install-row { display: flex; gap: 8px; margin-bottom: 6px; }
.input {
  flex: 1; padding: 6px 10px; background: var(--code-bg, #111); border: 1px solid var(--border, #333);
  border-radius: 5px; color: var(--text, #eee); font-size: 12px;
}
.install-hint { font-size: 10px; color: var(--text2, #555); }
.install-hint code { color: var(--cyan, #22d3ee); }
</style>
