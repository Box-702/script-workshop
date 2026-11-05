<template>
  <div class="home">
    <!-- 背景水印：巨大的「问」——品牌设计就是在这个问字上做的文章 -->
    <div class="home-watermark" aria-hidden="true">问</div>

    <!-- 顶栏：品牌 + 设置 -->
    <div class="home-top">
      <div class="home-brand">
        <LogoMark :size="22" />
        <span class="brand-name">问剧</span>
        <span class="brand-mode">WENJU</span>
      </div>
      <div class="home-top-actions">
        <button class="ghost small" @click="store.showNewProject = true"><AppIcon name="plus" /> 新建作品</button>
        <button class="ghost small" title="设置" @click="store.showSettings = true">
          <AppIcon name="gear" />
        </button>
      </div>
    </div>

    <!-- 主体：品牌命题 + 作品 -->
    <div class="home-main">
      <section class="home-hero" aria-label="问剧">
        <div class="mark-row">
          <span class="mark-badge" aria-hidden="true">
            <LogoMark :size="34" />
          </span>
          <h1 class="home-title">问剧</h1>
        </div>
        <p class="home-tagline">把一部小说，变成一部短剧。</p>
        <p class="home-hint">新建作品导入小说原文，AI 从剧本、人物白模、场景图一路做到提示词；什么时候出视频，由你决定。</p>
      </section>

      <section class="home-works" aria-label="我的作品">
        <div class="works-head">
          <span class="works-title">我的作品</span>
          <span class="works-count">{{ works.length ? `${works.length} 部` : '' }}</span>
        </div>

        <div class="works-grid">
          <!-- 新建作品卡片 -->
          <button class="work-card new-card" @click="store.showNewProject = true">
            <span class="new-plus" aria-hidden="true"><AppIcon name="plus" /></span>
            <span class="new-text">新建作品</span>
            <span class="new-sub">导入小说原文</span>
          </button>

          <!-- 历史作品卡片 -->
          <article v-for="p in works" :key="p.id" class="work-card" @click="enter(p.id)">
            <div class="work-cover" aria-hidden="true">
              <span class="work-glyph">{{ (p.title || '问')[0] }}</span>
            </div>
            <div class="work-body">
              <h3 class="work-title">{{ p.title }}</h3>
              <p class="work-meta">
                {{ formatDate(p.created_at) }} · 剧本 {{ p.version_count || 0 }} 版 · 改编 {{ p.run_count || 0 }} 次
              </p>
            </div>
            <button
              class="work-del" title="删除作品" aria-label="删除作品"
              @click.stop="remove(p)"
            ><AppIcon name="close" /></button>
          </article>
        </div>

        <p v-if="!works.length" class="works-empty">
          还没有作品。新建一部，导入小说原文，一分钟内看到第一版剧本。
        </p>
      </section>
    </div>
  </div>
</template>

<script setup>
// =====================================================================
// HomePage.vue —— 品牌首页（退出工作区后的落点）
//
// 只放三样东西：品牌（问剧，设计长在「问」上）、我的作品（历史作品卡片）、
// 新建作品入口。点作品卡 = 进入工作区（store.mode 切换，三栏布局接管）。
// =====================================================================
import { computed } from 'vue'
import { store, selectProject, deleteProject } from '../stores/app.js'
import LogoMark from './LogoMark.vue'
import AppIcon from './AppIcon.vue'

const works = computed(() =>
  [...(store.projects || [])].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
)

function enter(pid) {
  // selectProject 会把 mode 切到 workspace（三栏布局接管渲染）。
  selectProject(pid)
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
}

async function remove(p) {
  if (!confirm(`确定删除《${p.title}》？其剧本、资产与对话会一并删除。`)) return
  await deleteProject(p.id)
}
</script>

<style scoped>
.home {
  position: relative; min-height: 100vh; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--bg, #0b0f14);
}
.home-watermark {
  position: absolute; right: -4vmin; top: -8vmin;
  font-size: 58vmin; line-height: 1; font-weight: 700;
  color: transparent; -webkit-text-stroke: 1px color-mix(in oklch, var(--ink) 8%, transparent);
  user-select: none; pointer-events: none; z-index: 0;
}

.home-top {
  position: relative; z-index: 1;
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 26px;
}
.home-brand { display: flex; align-items: center; gap: 8px; }
.brand-name {
  font-size: 15px; font-weight: 600; color: var(--ink);
}
.brand-mode {
  color: var(--dim); font: 500 9px/1 var(--mono); letter-spacing: .1em;
}
.home-top-actions { display: flex; gap: 8px; }

.home-main {
  position: relative; z-index: 1;
  width: min(1060px, 92vw); margin: 0 auto;
  flex: 1; padding: 8vh 0 60px;
}

.home-hero { margin-bottom: 5vh; }
.mark-row { display: flex; align-items: center; gap: 14px; }
.mark-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 52px; height: 52px; border-radius: 10px;
  border: 1px solid var(--line-strong);
  background: var(--panel);
}
.mark-badge svg { width: 30px; height: 30px; }
.home-title {
  margin: 0; font-size: 40px; font-weight: 650; letter-spacing: .01em;
  color: var(--ink);
}
.home-tagline { margin: 14px 0 6px; font-size: 16px; font-weight: 650; color: var(--ink); }
.home-hint { margin: 0; font-size: 12.5px; color: var(--muted); max-width: 560px; line-height: 1.8; }

.works-head {
  display: flex; align-items: baseline; gap: 8px;
  margin: 0 0 12px; padding-top: 3vh;
  border-top: 1px solid color-mix(in oklch, var(--line) 55%, transparent);
}
.works-title {
  font-size: 10px; font-weight: 650; color: var(--dim);
  text-transform: uppercase; letter-spacing: .14em;
}
.works-count { font-size: 11px; color: var(--dim); font-variant-numeric: tabular-nums; }

.works-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px;
}
.work-card {
  position: relative; text-align: left;
  display: flex; flex-direction: column;
  border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
  background: var(--panel);
  cursor: pointer; padding: 0;
  transition: border-color 130ms var(--ease);
}
.work-card:hover {
  border-color: var(--line-strong);
}
.work-cover {
  display: flex; align-items: center; justify-content: center;
  aspect-ratio: 16 / 7;
  background: var(--panel2);
}
.work-glyph {
  font-size: 40px; font-weight: 600; color: var(--dim);
}
.work-body { padding: 12px 14px 14px; }
.work-title {
  margin: 0 0 4px; font-size: 14px; font-weight: 700; color: var(--ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.work-meta { margin: 0; font-size: 11px; color: var(--dim); font-variant-numeric: tabular-nums; }
.work-del {
  position: absolute; right: 8px; top: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 6px;
  border: 1px solid var(--line); background: color-mix(in oklch, var(--bg) 80%, transparent);
  color: var(--muted); font-size: 12px; line-height: 1;
  opacity: 0; cursor: pointer; transition: opacity 140ms var(--ease);
}
.work-card:hover .work-del { opacity: 1; }
.work-del:hover { color: #e5776f; border-color: #e5776f; }

.new-card {
  align-items: center; justify-content: center; gap: 4px;
  min-height: 150px;
  border-style: dashed; background: transparent;
}
.new-card:hover {
  background: color-mix(in oklch, var(--gold) 4%, transparent);
  border-color: color-mix(in oklch, var(--gold) 38%, var(--line));
}
.new-plus { display: inline-flex; font-size: 28px; color: var(--gold); line-height: 1; }
.new-text { font-size: 13.5px; font-weight: 700; color: var(--ink); }
.new-sub { font-size: 11px; color: var(--dim); }

.works-empty { margin: 18px 2px; font-size: 12.5px; color: var(--dim); }
</style>
