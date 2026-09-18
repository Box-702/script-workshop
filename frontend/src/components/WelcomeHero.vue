<script setup>
// =====================================================================
// WelcomeHero.vue —— 片场首页
//
// 初始页只保留一个主命题、一个主动作和一组轻量快捷动作。
// 把功能从「四张同权重卡片」改成「作品氛围 + 创作入口」。
// =====================================================================

import { computed } from 'vue'
import { store } from '../stores/app'
import LogoMark from './LogoMark.vue'

const projectName = computed(
  () => store.projects.find((p) => p.id === store.pid)?.title || ''
)

const hasProject = computed(() => Boolean(store.pid))

const quickActions = computed(() => (
  hasProject.value
    ? [
        { index: '01', title: '继续生成', desc: '从当前剧本继续推进', fill: '生成初稿' },
        { index: '02', title: '拆解分镜', desc: '把场景变成可生成镜头', fill: '帮我把当前故事拆解成可生成的分镜' },
        { index: '03', title: '打磨对白', desc: '让台词更口语、更像人说话', fill: '把当前剧本的对白改得更口语一点' },
      ]
    : [
        { index: '01', title: '导入原著', desc: '上传 .txt / .md / .docx 文件', open: 'newProject' },
        { index: '02', title: '粘贴片段', desc: '从一段文字直接开始', open: 'newProject' },
        { index: '03', title: '了解 Agent', desc: '看看它可以怎样帮你', fill: '你能帮我做什么？' },
      ]
))

function fill(text) {
  store.draft = text
  store.draftSeq++
}

function startPrimary() {
  if (hasProject.value) fill('生成初稿')
  else store.showNewProject = true
}

function startSecondary() {
  if (hasProject.value) fill('帮我把当前故事拆解成可生成的分镜')
  else fill('你能帮我做什么？')
}

function onQuickAction(action) {
  if (action.fill) fill(action.fill)
  if (action.open === 'newProject') store.showNewProject = true
}
</script>

<template>
  <section class="hero" aria-label="开始创作">
    <div class="hero-backdrop" aria-hidden="true">
      <div class="hero-image"></div>
      <div class="hero-vignette"></div>
      <div class="hero-grid"></div>
    </div>

    <div class="hero-top">
      <div class="hero-brandline">
        <span class="hero-brandmark"><LogoMark :size="20" /></span>
        <span>STORY WORKSHOP</span>
        <i></i>
        <span>{{ hasProject ? 'CURRENT PROJECT' : 'NEW STORY' }}</span>
      </div>
      <div class="hero-status">
        <span class="status-dot"></span>
        READY TO CREATE
      </div>
    </div>

    <div class="hero-main">
      <div class="hero-copy">
        <p class="hero-kicker">AI VIDEO STORY STUDIO</p>
        <h2 class="hero-title">
          <template v-if="hasProject">继续把《{{ projectName }}》拍出来</template>
          <template v-else>从一个故事，开始你的第一场戏</template>
        </h2>
        <p class="hero-sub">
          <template v-if="hasProject">剧本、分镜、提示词和成片，都从当前对话继续。</template>
          <template v-else>导入原著或粘贴片段，让 Agent 先帮你搭起故事的骨架。</template>
        </p>

        <div class="hero-actions">
          <button class="primary-action" @click="startPrimary">
            <span>{{ hasProject ? '生成初稿' : '开始一个新故事' }}</span>
            <span aria-hidden="true">↗</span>
          </button>
          <button class="secondary-action" @click="startSecondary">
            {{ hasProject ? '先拆解分镜' : '先和 Agent 聊聊' }}
          </button>
        </div>
      </div>

      <div class="hero-note">
        <span class="note-index">01 / 03</span>
        <strong>{{ hasProject ? '从剧本到镜头' : '从灵感到成片' }}</strong>
        <span>Agent 会在每一步停下来，让你决定下一步。</span>
      </div>
    </div>

    <div class="hero-bottom">
      <div class="hero-flow">
        <span class="flow-label">WORKFLOW</span>
        <span>STORY</span>
        <i></i>
        <span>SHOT</span>
        <i></i>
        <span>VIDEO</span>
      </div>

      <div class="quick-actions" role="list" aria-label="快捷动作">
        <button
          v-for="action in quickActions"
          :key="action.index"
          class="quick-action"
          role="listitem"
          @click="onQuickAction(action)"
        >
          <span class="quick-index">{{ action.index }}</span>
          <span class="quick-copy">
            <strong>{{ action.title }}</strong>
            <small>{{ action.desc }}</small>
          </span>
          <span class="quick-arrow" aria-hidden="true">↗</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  min-height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
  isolation: isolate;
  padding: 24px clamp(20px, 4vw, 56px) 24px;
  color: var(--ink);
}

.hero-backdrop,
.hero-image,
.hero-vignette,
.hero-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hero-backdrop { z-index: -2; background: var(--bg); }
.hero-image {
  background:
    url('https://blog-bk.sondo.ai/upload/2025/06/6870109c1e04b.webp') center / cover,
    url('https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=1400&q=80') center / cover;
  opacity: .58;
  filter: saturate(.88) contrast(1.04);
  transform: scale(1.025);
}
.hero-vignette {
  background:
    linear-gradient(90deg, color-mix(in oklch, var(--bg) 88%, transparent) 0%, color-mix(in oklch, var(--bg) 42%, transparent) 54%, color-mix(in oklch, var(--bg) 52%, transparent) 100%),
    linear-gradient(180deg, color-mix(in oklch, var(--bg) 56%, transparent) 0%, transparent 44%, color-mix(in oklch, var(--bg) 82%, transparent) 100%);
}
.hero-grid {
  opacity: .08;
  background-image:
    linear-gradient(color-mix(in oklch, var(--ink) 18%, transparent) 1px, transparent 1px),
    linear-gradient(90deg, color-mix(in oklch, var(--ink) 18%, transparent) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: linear-gradient(to bottom, black, transparent 80%);
}

.hero-top,
.hero-main,
.hero-bottom {
  position: relative;
  z-index: 1;
}

.hero-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: var(--muted);
  font: 600 10px/1 var(--mono);
  letter-spacing: .1em;
}
.hero-brandline,
.hero-status,
.hero-flow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.hero-brandline i,
.hero-flow i {
  width: 22px;
  height: 1px;
  background: var(--line-strong);
}
.hero-brandmark { display: inline-flex; color: var(--accent); margin-right: 2px; }
.hero-status { color: var(--dim); letter-spacing: .08em; }
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--cyan);
}

.hero-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 210px;
  align-items: end;
  gap: 48px;
  margin: auto 0;
  padding: 60px 0 72px;
}
.hero-copy { max-width: 600px; }
.hero-kicker {
  margin: 0 0 18px;
  color: var(--accent);
  font: 700 10px/1 var(--mono);
  letter-spacing: .16em;
}
.hero-title {
  max-width: 12ch;
  margin: 0;
  font-size: 42px;
  font-weight: 720;
  letter-spacing: -.025em;
  line-height: 1.08;
}
.hero-sub {
  max-width: 42ch;
  margin: 18px 0 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.7;
}
.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 26px;
}
.primary-action,
.secondary-action {
  min-height: 36px;
  border-radius: 8px;
}
.primary-action {
  display: inline-flex;
  align-items: center;
  gap: 18px;
  padding-inline: 13px 11px;
  background: var(--accent);
  color: var(--on-accent);
}
.primary-action:hover { background: var(--accent-hover); }
.secondary-action {
  padding-inline: 12px;
  background: color-mix(in oklch, var(--bg) 52%, transparent);
  border-color: color-mix(in oklch, var(--ink) 18%, var(--line));
  color: var(--muted);
}
.secondary-action:hover { color: var(--ink); border-color: var(--line-strong); background: color-mix(in oklch, var(--ink) 5%, transparent); }

.hero-note {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding-left: 16px;
  border-left: 1px solid color-mix(in oklch, var(--accent) 48%, var(--line));
  color: var(--muted);
  font-size: 11px;
  line-height: 1.55;
}
.hero-note strong { color: var(--ink); font-size: 13px; font-weight: 650; }
.note-index { color: var(--accent); font: 700 10px/1 var(--mono); letter-spacing: .08em; }

.hero-bottom {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 24px;
  align-items: end;
  padding-top: 14px;
  border-top: 1px solid color-mix(in oklch, var(--ink) 14%, transparent);
}
.hero-flow {
  align-self: start;
  color: var(--dim);
  font: 600 10px/1.4 var(--mono);
  letter-spacing: .08em;
}
.flow-label { color: var(--accent); }
.quick-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
}
.quick-action {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 4px 18px;
  border: 0;
  border-left: 1px solid var(--line);
  border-radius: 0;
  background: transparent;
  color: var(--muted);
  text-align: left;
}
.quick-action:last-child { border-right: 1px solid var(--line); }
.quick-action:hover { background: color-mix(in oklch, var(--ink) 4%, transparent); color: var(--ink); }
.quick-index {
  align-self: flex-start;
  color: var(--accent);
  font: 700 9px/1 var(--mono);
  letter-spacing: .08em;
}
.quick-copy { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.quick-copy strong { color: inherit; font-size: 12px; font-weight: 650; }
.quick-copy small { overflow: hidden; color: var(--dim); font-size: 10.5px; text-overflow: ellipsis; white-space: nowrap; }
.quick-arrow { margin-left: auto; color: var(--dim); font-size: 14px; }

@media (max-width: 900px) {
  .hero-main { grid-template-columns: 1fr; gap: 24px; padding: 48px 0 56px; }
  .hero-note { max-width: 320px; }
  .hero-bottom { grid-template-columns: 1fr; gap: 16px; }
}

@media (max-width: 620px) {
  .hero { padding: 18px 16px 18px; }
  .hero-brandline span:not(.hero-brandmark):nth-last-child(-n + 2) { display: none; }
  .hero-status { font-size: 9px; }
  .hero-main { padding: 50px 0 46px; }
  .hero-title { font-size: 30px; }
  .hero-sub { font-size: 13px; }
  .hero-actions { align-items: stretch; flex-direction: column; max-width: 240px; }
  .hero-actions button { justify-content: space-between; }
  .quick-actions { grid-template-columns: 1fr; }
  .quick-action,
  .quick-action:last-child { border-right: 0; border-left: 0; border-top: 1px solid var(--line); padding: 10px 0; }
  .quick-action:last-child { border-bottom: 1px solid var(--line); }
}
</style>
