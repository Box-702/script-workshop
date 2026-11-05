<template>
  <div class="asset-panel">
    <!-- 作品：进入工作区的唯一入口（每个作品一个工作区，工作区内只有一个对话） -->
    <div class="panel-section">
      <div class="section-head">
        <span class="section-title">作品</span>
        <button class="btn-new" @click="store.showNewProject = true" title="新建作品（导入小说原文）" aria-label="新建作品"><AppIcon name="plus" /></button>
      </div>
      <div
        v-for="p in projects" :key="p.id"
        :class="['proj-item', { active: store.pid === p.id }]"
        @click="enterWorkspace(p.id)"
      >
        <span class="proj-name">{{ p.title }}</span>
      </div>
      <div v-if="!projects.length" class="proj-empty">
        <p>还没有作品。新建一部，导入小说原文就开始。</p>
      </div>
    </div>

    <!-- 资产库：当前作品的角色白模与场景图（提示词里的映射编号来自这里的 id） -->
    <div v-if="store.pid" class="panel-section library-section">
      <div class="section-head">
        <span class="section-title">资产库</span>
        <button class="btn-tiny" @click="loadLibrary" title="刷新" aria-label="刷新">⟳</button>
      </div>

      <div v-if="lib.loading" class="lib-empty">加载中…</div>
      <template v-else>
        <div class="lib-label">人物（{{ lib.characters.length }}）</div>
        <div class="asset-grid">
          <div v-for="c in lib.characters" :key="c.char_id" class="asset-card" :title="c.appearance || c.name">
            <img v-if="c.image" :src="c.image" :alt="c.name" loading="lazy" />
            <div v-else class="asset-placeholder">白模</div>
            <span class="asset-name">{{ c.name }}</span>
            <span class="asset-id">{{ c.char_id }}</span>
          </div>
        </div>

        <div class="lib-label">场景（{{ lib.locations.length }}）</div>
        <div class="asset-grid">
          <div v-for="l in lib.locations" :key="l.loc_id" class="asset-card" :title="l.description || l.name">
            <img v-if="l.image" :src="l.image" :alt="l.name" loading="lazy" />
            <div v-else class="asset-placeholder">场景图</div>
            <span class="asset-name">{{ l.name }}</span>
            <span class="asset-id">{{ l.loc_id }}</span>
          </div>
        </div>

        <div v-if="!lib.characters.length && !lib.locations.length" class="lib-empty">
          还没有资产。点下方「开始制作」，流水线会生成人物白模与场景图。
        </div>

        <button class="produce-btn" :disabled="producing" @click="startProduction">
          <AppIcon :name="producing ? 'pause' : 'play'" /> {{ producing ? '制作中…' : '开始制作（剧本→资产→提示词）' }}
        </button>
      </template>
    </div>

    <!-- 未选中作品：提示进入 -->
    <div v-else class="lib-empty" style="padding: 18px 14px;">
      左侧选择一部作品进入工作区；资产库会显示这部作品的人物与场景。
    </div>
  </div>
</template>

<script setup>
// =====================================================================
// AssetPanel.vue —— 左栏：作品入口 + 资产库
//
// 改版说明（工作区化）：原来这里是「对话列表」（全局会话 + 每项目多会话），
// 现在对话收敛为每作品一个（进入作品自动用默认会话），左栏让给资产库——
// 对话里引用的每个人物白模 / 场景图都能在这里按编号找到原图。
// =====================================================================
import { computed, reactive, ref, watch } from 'vue'
import { store, selectProject, notify, loadShots } from '../stores/app.js'
import { api } from '../api.js'
import AppIcon from './AppIcon.vue'

const projects = computed(() => store.projects)
const lib = reactive({ loading: false, characters: [], locations: [], warnings: [] })
const producing = ref(false)

function enterWorkspace(pid) {
  if (store.pid === pid) return
  selectProject(pid)
}

async function loadLibrary() {
  if (!store.pid) return
  lib.loading = true
  try {
    const data = await api(`/projects/${store.pid}/library`)
    lib.characters = data.characters || []
    lib.locations = data.locations || []
    lib.warnings = data.warnings || []
  } catch (e) {
    notify('资产库加载失败：' + e.message)
  } finally {
    lib.loading = false
  }
}

async function startProduction() {
  if (!store.pid || producing.value) return
  producing.value = true
  try {
    const r = await api(`/projects/${store.pid}/production`, 'POST')
    notify('生产流水线已启动，完成后提示词进入待审', 'ok')
    // 轮询任务状态：结束后刷新资产库与右栏镜头（提示词版本已更新）。
    const taskId = r.task_id
    const timer = setInterval(async () => {
      try {
        const t = await api(`/tasks/${taskId}`)
        if (t.status === 'done' || t.status === 'failed') {
          clearInterval(timer)
          producing.value = false
          if (t.status === 'failed') notify('流水线失败：' + (t.result || ''))
          else notify('流水线完成：' + (t.result || ''), 'ok')
          await loadLibrary()
          await loadShots()
        }
      } catch { clearInterval(timer); producing.value = false }
    }, 3000)
  } catch (e) {
    notify('启动失败：' + e.message)
    producing.value = false
  }
}

// 进入新作品 / 资产可能被流水线更新 → 重新拉资产库
watch(() => store.pid, (pid) => { if (pid) loadLibrary() }, { immediate: true })
</script>

<style scoped>
.asset-panel { display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
.panel-section { padding: 4px 0 10px; }
.library-section { border-top: 1px solid color-mix(in oklch, var(--line) 55%, transparent); }
.section-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 14px 6px;
}
.section-title {
  font-size: 9.5px; font-weight: 650; color: var(--dim);
  text-transform: uppercase; letter-spacing: .14em;
}
.btn-new {
  width: 28px; height: 28px; border-radius: 7px;
  border: 1px solid var(--line); background: transparent;
  color: var(--muted); cursor: pointer; font-size: 12px; line-height: 1;
  display: flex; align-items: center; justify-content: center; padding: 0;
  transition: color 150ms var(--ease), border-color 150ms var(--ease), background 150ms var(--ease);
}
.btn-new:hover {
  border-color: color-mix(in oklch, var(--gold) 45%, var(--line));
  color: var(--gold); background: var(--gold-soft);
}
.btn-tiny {
  background: transparent; border: none; border-radius: 4px;
  cursor: pointer; font-size: 12px; padding: 4px 6px;
  opacity: .55; color: var(--muted); transition: opacity 120ms, background 120ms;
}
.btn-tiny:hover { opacity: 1; background: color-mix(in oklch, var(--ink) 8%, transparent); }

.proj-item {
  position: relative;
  display: flex; align-items: center; padding: 10px 12px 10px 14px;
  margin: 1px 6px; border-radius: 8px;
  cursor: pointer; font-size: 12.5px; color: var(--muted);
  transition: background .14s var(--ease), color .14s var(--ease);
}
.proj-item:hover { background: color-mix(in oklch, var(--ink) 5%, transparent); color: var(--ink); }
.proj-item.active {
  background: color-mix(in oklch, var(--gold) 9%, transparent); color: var(--ink);
}
.proj-item.active::before {
  content: ''; position: absolute; left: 0; top: 7px; bottom: 7px; width: 2px;
  border-radius: 2px; background: var(--gold);
}
.proj-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.proj-empty { padding: 10px 14px; font-size: 12px; color: var(--dim); line-height: 1.7; }

.lib-label {
  padding: 10px 14px 4px;
  font-size: 11px; font-weight: 650; color: var(--muted);
}
.asset-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px;
  padding: 4px 12px;
}
.asset-card {
  position: relative; border: 1px solid var(--line); border-radius: 8px;
  overflow: hidden; background: color-mix(in oklch, var(--ink) 4%, transparent);
  cursor: default;
}
.asset-card img {
  display: block; width: 100%; aspect-ratio: 3 / 4; object-fit: cover;
}
.asset-placeholder {
  display: flex; align-items: center; justify-content: center;
  width: 100%; aspect-ratio: 3 / 4;
  color: var(--dim); font-size: 11px; letter-spacing: .08em;
}
.asset-name {
  position: absolute; left: 6px; bottom: 5px; right: 6px;
  font-size: 10.5px; font-weight: 650; color: #fff;
  text-shadow: 0 1px 3px rgb(0 0 0 / 70%);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.asset-id {
  position: absolute; right: 4px; top: 4px;
  font-size: 8.5px; color: rgb(255 255 255 / 85%);
  background: rgb(0 0 0 / 45%); border-radius: 4px; padding: 1px 4px;
  font-variant-numeric: tabular-nums;
}
.lib-empty { padding: 8px 14px; font-size: 11.5px; color: var(--dim); line-height: 1.7; }
.produce-btn {
  display: block; width: calc(100% - 24px); margin: 10px 12px 4px;
  min-height: 38px; border-radius: 9px;
  border: 1px solid color-mix(in oklch, var(--gold) 40%, var(--line));
  background: var(--gold-soft); color: var(--gold);
  cursor: pointer; font-size: 12px; font-weight: 650;
  transition: filter 150ms var(--ease), transform 100ms var(--ease);
}
.produce-btn:hover:not(:disabled) { filter: brightness(1.08); }
.produce-btn:active:not(:disabled) { transform: scale(.985); }
.produce-btn:disabled { opacity: .6; cursor: default; }
</style>
