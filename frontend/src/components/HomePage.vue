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
        <button class="ghost small" @click="store.showNewProject = true">＋ 新建作品</button>
        <button class="ghost small" title="设置" @click="store.showSettings = true">
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <circle cx="8" cy="8" r="2.2" />
            <path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2M3.6 3.6l1.4 1.4M11 11l1.4 1.4M12.4 3.6L11 5M5 11l-1.4 1.4" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 主体：品牌命题 + 作品 -->
    <div class="home-main">
      <section class="home-hero" aria-label="问剧">
        <div class="mark-row">
          <span class="mark-badge" aria-hidden="true">
            <!-- 问号设计：问号的点换成了播放键——「问出一个故事，然后看它发生」 -->
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M8.4 6.2c.9-1.5 2.5-2.2 4.2-2 2.2.2 3.8 1.7 3.8 3.7 0 2.7-3.4 3-3.4 5.6"
                    stroke="currentColor" stroke-width="1.9" stroke-linecap="round" />
              <path d="M10.2 17.4 14 15.2v4.4z" fill="currentColor" />
            </svg>
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
            <span class="new-plus" aria-hidden="true">＋</span>
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
            >×</button>
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
  background:
    radial-gradient(120% 90% at 78% -10%, color-mix(in oklch, var(--gold) 7%, transparent), transparent 60%),
    var(--bg, #0b0f14);
}
.home-watermark {
  position: absolute; right: -4vmin; top: -8vmin;
  font-size: 58vmin; line-height: 1; font-weight: 800;
  color: transparent; -webkit-text-stroke: 1.5px color-mix(in oklch, var(--ink) 13%, transparent);
  user-select: none; pointer-events: none; z-index: 0;
}

.home-top {
  position: relative; z-index: 1;
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 26px;
}
.home-brand { display: flex; align-items: center; gap: 8px; }
.brand-name {
  font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 15px; font-weight: 800; color: var(--ink);
  background: linear-gradient(97deg, var(--ink) 25%, var(--gold-glow) 62%, var(--ink) 95%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.brand-mode {
  color: var(--gold); font: 600 9px/1 var(--mono); letter-spacing: .12em;
  padding: 4px 5px; border: 1px solid color-mix(in oklch, var(--gold) 35%, var(--line));
  border-radius: 5px;
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
  width: 52px; height: 52px; border-radius: 14px;
  border: 1px solid color-mix(in oklch, var(--gold) 40%, var(--line));
  background: color-mix(in oklch, var(--gold) 8%, transparent);
  color: var(--gold);
}
.mark-badge svg { width: 30px; height: 30px; }
.home-title {
  margin: 0; font-size: 46px; font-weight: 800; letter-spacing: .02em;
  background: linear-gradient(97deg, var(--ink) 30%, var(--gold-glow) 62%, var(--ink) 95%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
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
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
  background: color-mix(in oklch, var(--panel) 88%, transparent);
  cursor: pointer; padding: 0;
  transition: border-color 160ms var(--ease), transform 160ms var(--ease), box-shadow 160ms var(--ease);
}
.work-card:hover {
  border-color: color-mix(in oklch, var(--gold) 45%, var(--line));
  transform: translateY(-2px);
  box-shadow: 0 10px 30px color-mix(in oklch, #000 30%, transparent);
}
.work-cover {
  display: flex; align-items: center; justify-content: center;
  aspect-ratio: 16 / 7;
  background:
    radial-gradient(90% 120% at 30% 0%, color-mix(in oklch, var(--gold) 12%, transparent), transparent 70%),
    color-mix(in oklch, var(--ink) 6%, transparent);
}
.work-glyph {
  font-size: 44px; font-weight: 800; color: color-mix(in oklch, var(--gold) 65%, var(--ink));
  opacity: .85;
}
.work-body { padding: 12px 14px 14px; }
.work-title {
  margin: 0 0 4px; font-size: 14px; font-weight: 700; color: var(--ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.work-meta { margin: 0; font-size: 11px; color: var(--dim); font-variant-numeric: tabular-nums; }
.work-del {
  position: absolute; right: 8px; top: 8px;
  width: 24px; height: 24px; border-radius: 6px;
  border: 1px solid var(--line); background: color-mix(in oklch, var(--bg) 80%, transparent);
  color: var(--muted); font-size: 13px; line-height: 1;
  opacity: 0; cursor: pointer; transition: opacity 140ms var(--ease);
}
.work-card:hover .work-del { opacity: 1; }
.work-del:hover { color: #e5776f; border-color: #e5776f; }

.new-card {
  align-items: center; justify-content: center; gap: 4px;
  min-height: 150px;
  border-style: dashed; background: transparent;
}
.new-plus { font-size: 30px; color: var(--gold); line-height: 1; }
.new-text { font-size: 13.5px; font-weight: 700; color: var(--ink); }
.new-sub { font-size: 11px; color: var(--dim); }

.works-empty { margin: 18px 2px; font-size: 12.5px; color: var(--dim); }
</style>
