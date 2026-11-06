<template>
  <div class="asset-panel">
    <!-- 新建作品 -->
    <div v-if="section === 'all'" class="panel-section">
      <button class="new-task" @click="store.showNewProject = true">
        <AppIcon name="plus" />
        <span>新建作品</span>
      </button>
    </div>

    <!-- 技能：主 Agent 能加载的技能；点一下预填进输入框 -->
    <div v-if="section === 'all'" class="panel-section">
      <div class="section-head">
        <span class="section-title">技能</span>
      </div>
      <button
        v-for="s in store.skills" :key="s.name"
        class="skill-item"
        :title="s.description"
        @click="useSkill(s)"
      >
        <span class="skill-name">{{ s.name }}</span>
        <span class="skill-desc">{{ s.description }}</span>
      </button>
      <div v-if="!store.skills.length" class="proj-empty">
        <p>没有可用技能。</p>
      </div>
    </div>

    <!-- 作品列表（每个作品一个工作区） -->
    <div v-if="section === 'all' || section === 'tasks'" class="panel-section">
      <div class="section-head">
        <span class="section-title">我的作品</span>
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
    <div v-if="store.pid && (section === 'all' || section === 'assets')" class="panel-section library-section">
      <div class="section-head">
        <span class="section-title">资产库</span>
        <span class="head-tools">
          <input
            ref="importInput"
            type="file"
            accept="image/*,video/*"
            multiple
            hidden
            @change="onImportChosen"
          />
          <button class="btn-tiny" :disabled="importing" @click="importInput?.click()" title="导入图片/视频">
            <AppIcon name="upload" /> {{ importing ? '导入中…' : '导入' }}
          </button>
          <button class="btn-tiny" @click="loadLibrary" title="刷新" aria-label="刷新">⟳</button>
        </span>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { store, selectProject, notify, loadShots } from '../stores/app.js'
import { loadSkills, useSkill } from '../stores/app'
import { api, uploadAsset } from '../api.js'
import AppIcon from './AppIcon.vue'

const projects = computed(() => store.projects)
const props = defineProps({
  /** 显示哪一段：tasks = 我的作品（作品列表）；assets = 资产库 */
  section: { type: String, default: 'all' },
})

const lib = reactive({ loading: false, characters: [], locations: [], warnings: [] })

// ---- 导入素材 ----
const importInput = ref(null)
const importing = ref(false)

async function onImportChosen(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''
  if (!files.length || !store.pid) return
  importing.value = true
  try {
    for (const file of files) {
      await uploadAsset(store.pid, file)
    }
    notify(`已导入 ${files.length} 个素材`, 'ok')
    await loadLibrary()
  } catch (err) {
    notify(`导入失败：${err.message}`)
  } finally {
    importing.value = false
  }
}
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
onMounted(() => { loadSkills() })

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

/* 新任务入口 */
.new-task {
  display: flex; align-items: center; gap: 9px;
  width: 100%; padding: 9px 11px; border-radius: 10px;
  background: rgba(255, 255, 255, .05); border: 1px solid var(--line);
  color: var(--ink); font-size: 13px; font-family: inherit; cursor: pointer;
  transition: background 130ms var(--ease), border-color 130ms var(--ease);
}
.new-task:hover {
  background: rgba(255, 255, 255, .1); border-color: var(--line-strong);
}
.new-task .app-ic { opacity: .8; }

/* 技能条目 */
.skill-item {
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  width: 100%; padding: 7px 10px; border-radius: 9px;
  background: transparent; border: 1px solid transparent;
  color: var(--muted); font-family: inherit; text-align: left; cursor: pointer;
  transition: background 130ms var(--ease), color 130ms var(--ease);
}
.skill-item:hover {
  background: rgba(255, 255, 255, .07); color: var(--ink);
}
.skill-name {
  font-size: 12.5px; font-weight: 500; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;
}
.skill-desc {
  font-size: 11px; line-height: 1.45; color: var(--dim);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}

.head-tools { display: inline-flex; align-items: center; gap: 6px; }
.head-tools .btn-tiny { display: inline-flex; align-items: center; gap: 4px; }
.head-tools .app-ic { width: 12px; height: 12px; }

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
  background: var(--accent-grad); color: var(--on-accent); border-color: transparent;
  box-shadow: 0 8px 24px rgba(34, 197, 94, .26);
  display: block; width: calc(100% - 24px); margin: 10px 12px 4px;
  min-height: 38px; border-radius: 9px;
  border: 1px solid transparent;
  cursor: pointer; font-size: 12px; font-weight: 650;
  transition: filter 150ms var(--ease), transform 100ms var(--ease);
}
.produce-btn:hover:not(:disabled) { filter: brightness(1.08); }
.produce-btn:active:not(:disabled) { transform: scale(.985); }
.produce-btn:disabled { opacity: .6; cursor: default; }
</style>
