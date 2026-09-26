<script setup>
// =====================================================================
// WelcomeHero.vue —— 首次创作开始页（只在「无项目 + 无对话」的首创态出现）
//
// 一个主命题 + 一主一次两个动作 + 三个示例模板 + 语义化流程条。
// 与编辑态（已有项目 / 进行中的对话）完全分流：编辑态的空对话
// 由 ChatThread 渲染轻量空态，不再回到这张大开始页。
// =====================================================================

import { store, focusComposer } from '../stores/app'
import LogoMark from './LogoMark.vue'

// 三个示例模板：点击只把示例填进输入框（不自动发送），由用户确认后发出。
const TEMPLATES = [
  {
    index: '01',
    tag: '从一个想法',
    text: '一个失去记忆的出租车司机，在雨夜接到未来的自己。',
  },
  {
    index: '02',
    tag: '从一段原文',
    text: '把我贴进项目里的那段原文改编成 3 分钟短剧，保留原著的语气和节奏。',
  },
  {
    index: '03',
    tag: '从一个人物',
    text: '从人物开始：一个总在深夜出诊的乡村兽医，想退休却总被叫回去。',
  },
]

// 流程条：语义化的四步（有序列表，屏幕阅读器读作「第 1 步 / 共 4 步」）。
const FLOW_STEPS = ['想法', '剧本', '分镜', '成片']

function useTemplate(t) {
  store.draft = t.text
  store.draftSeq++
}
</script>

<template>
  <section class="hero" aria-label="开始创作">
    <div class="hero-backdrop" aria-hidden="true">
      <div class="hero-image"></div>
      <div class="hero-vignette"></div>
    </div>

    <div class="hero-main">
      <p class="hero-kicker">
        <span class="hero-brandmark" aria-hidden="true"><LogoMark :size="18" /></span>
        AI VIDEO STORY STUDIO
      </p>
      <h2 class="hero-title">把一个想法，变成一场戏</h2>
      <p class="hero-sub">
        从一句灵感、一段原文或一个人物开始，AI 会先搭出故事骨架，再带你进入镜头创作。
      </p>

      <div class="hero-actions">
        <button class="primary-action" @click="focusComposer()">从想法开始</button>
        <button class="secondary-action" @click="store.showNewProject = true">导入文档</button>
      </div>

      <!-- 三个示例模板：填入输入框，不自动发送 -->
      <div class="templates" role="list" aria-label="示例模板">
        <button
          v-for="t in TEMPLATES"
          :key="t.index"
          class="template-chip"
          role="listitem"
          @click="useTemplate(t)"
        >
          <span class="template-index" aria-hidden="true">{{ t.index }}</span>
          <span class="template-copy">
            <strong>{{ t.tag }}</strong>
            <span class="template-text">{{ t.text }}</span>
          </span>
        </button>
      </div>
    </div>

    <!-- 流程条：想法 → 剧本 → 分镜 → 成片 -->
    <ol class="hero-flow" aria-label="创作流程">
      <li v-for="(step, i) in FLOW_STEPS" :key="step" :aria-setindex="i + 1">
        <span class="flow-num" aria-hidden="true">0{{ i + 1 }}</span>
        <span class="flow-name">{{ step }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.hero {
  min-height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--space-6);
  overflow: hidden;
  isolation: isolate;
  padding: var(--space-6) clamp(var(--space-4), 4vw, var(--space-7)) var(--space-5);
  color: var(--ink);
}

.hero-backdrop,
.hero-image,
.hero-vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hero-backdrop { z-index: -2; background: var(--bg); }
.hero-image {
  background:
    url('https://blog-bk.sondo.ai/upload/2025/06/6870109c1e04b.webp') center / cover,
    url('https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=1400&q=80') center / cover;
  opacity: .55;
  filter: saturate(.88) contrast(1.04);
  transform: scale(1.025);
}
.hero-vignette {
  background:
    linear-gradient(90deg, color-mix(in oklch, var(--bg) 88%, transparent) 0%, color-mix(in oklch, var(--bg) 42%, transparent) 54%, color-mix(in oklch, var(--bg) 52%, transparent) 100%),
    linear-gradient(180deg, color-mix(in oklch, var(--bg) 56%, transparent) 0%, transparent 44%, color-mix(in oklch, var(--bg) 82%, transparent) 100%);
}

.hero-main { max-width: 640px; }

.hero-kicker {
  margin: 0 0 var(--space-4);
  display: inline-flex; align-items: center; gap: var(--space-2);
  color: var(--accent);
  font: 700 var(--fs-xs)/1 var(--mono);
  letter-spacing: .16em;
}
.hero-brandmark { display: inline-flex; }

.hero-title {
  margin: 0;
  font-size: clamp(var(--fs-xl), 5vw, var(--fs-display));
  font-weight: 720;
  letter-spacing: -.02em;
  line-height: var(--lh-tight);
}

.hero-sub {
  max-width: 44ch;
  margin: var(--space-4) 0 0;
  color: var(--muted);
  font-size: var(--fs-md);
  line-height: var(--lh-body);
}

/* 主 / 次动作：点击目标 ≥44px */
.hero-actions {
  display: flex; align-items: center; gap: var(--space-3);
  margin-top: var(--space-5);
  flex-wrap: wrap;
}
.primary-action {
  min-height: var(--tap);
  padding: 0 var(--space-5);
  border-radius: var(--radius-md);
  font-size: var(--fs-md);
  font-weight: 650;
}
.secondary-action {
  min-height: var(--tap);
  padding: 0 var(--space-4);
  background: transparent;
  border: 1px solid var(--line-strong);
  color: var(--muted);
  border-radius: var(--radius-md);
  font-size: var(--fs-md);
  font-weight: 550;
}
.secondary-action:hover:not(:disabled) {
  background: transparent; color: var(--ink);
  border-color: color-mix(in oklch, var(--gold) 45%, var(--line-strong));
}

/* 示例模板：安静的横向 chips，填入输入框 */
.templates {
  display: flex; flex-direction: column; gap: var(--space-2);
  margin-top: var(--space-5);
}
.template-chip {
  display: flex; align-items: baseline; gap: var(--space-3);
  min-height: var(--tap);
  padding: var(--space-2) var(--space-3);
  text-align: left;
  background: color-mix(in oklch, var(--panel) 62%, transparent);
  border: 1px solid color-mix(in oklch, var(--line) 72%, transparent);
  border-radius: var(--radius-md);
  color: var(--muted);
  font-weight: 400;
  backdrop-filter: none;
  transition: border-color var(--dur) var(--ease), color var(--dur) var(--ease), background var(--dur) var(--ease);
}
.template-chip:hover:not(:disabled) {
  color: var(--ink);
  border-color: color-mix(in oklch, var(--gold) 40%, var(--line));
  background: color-mix(in oklch, var(--panel) 82%, transparent);
}
.template-index { flex: none; font: 650 var(--fs-xs)/1.6 var(--mono); color: var(--gold); }
.template-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.template-copy strong { font-size: var(--fs-sm); font-weight: 650; color: var(--ink); }
.template-text {
  font-size: var(--fs-sm);
  color: var(--muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* 流程条：语义化 ol，减少装饰 */
.hero-flow {
  list-style: none;
  margin: 0; padding: var(--space-3) 0 0;
  border-top: 1px solid color-mix(in oklch, var(--line) 60%, transparent);
  display: flex; align-items: center; gap: var(--space-5);
  flex-wrap: wrap;
}
.hero-flow li { display: inline-flex; align-items: baseline; gap: var(--space-2); }
.flow-num { font: 650 var(--fs-xs)/1 var(--mono); color: var(--gold); }
.flow-name { font-size: var(--fs-sm); color: var(--muted); font-weight: 550; }

@media (max-width: 640px) {
  .hero { padding: var(--space-5) var(--space-4); }
  .template-text { white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .hero-flow { gap: var(--space-4); }
}
</style>
