<script setup>
// =====================================================================
// WelcomeHero.vue —— 开始页（3D 卡片 + 渐变色 + 动效）
// =====================================================================

import { computed } from 'vue'
import { store } from '../stores/app'
import LogoMark from './LogoMark.vue'

const projectName = computed(
  () => store.projects.find((p) => p.id === store.pid)?.title || ''
)

function fill(text) { store.draft = text; store.draftSeq++ }

const CREATE_CARDS = [
  { icon: 'upload', title: '上传原著文件', desc: '.txt / .md / .docx，导入即建知识库', open: 'newProject', hue: 'gold' },
  { icon: 'doc', title: '粘贴文本开始', desc: '复制一段小说，也能直接生成初稿', open: 'newProject', hue: 'violet' },
  { icon: 'folder', title: '设置工作目录', desc: '剧本以真实文件落盘，随时打开', open: 'workspace', hue: 'cyan' },
  { icon: 'help', title: '它能做什么？', desc: '问问 Agent 的工作方式与边界', fill: '你能帮我做什么？', hue: 'rose' },
]
const PROJECT_CARDS = [
  { icon: 'pen', title: '生成初稿', desc: '从原著产出结构化剧本', fill: '生成初稿', hue: 'gold' },
  { icon: 'bubble', title: '打磨对白', desc: '把对白改得更口语、更像人说话', fill: '把对白改口语一点', hue: 'violet' },
  { icon: 'pace', title: '调整节奏', desc: '节奏改紧凑一点，保留原结构', fill: '节奏改紧凑一点', hue: 'cyan' },
  { icon: 'search', title: '检索项目知识', desc: '同类剧的走向、手法与作者风格', fill: '这类悬疑剧怎么设计反转？', hue: 'rose' },
]
const cards = computed(() => (store.pid ? PROJECT_CARDS : CREATE_CARDS))

function onCard(card) {
  if (card.fill) return fill(card.fill)
  if (card.open === 'newProject') store.showNewProject = true
  if (card.open === 'workspace') store.showWorkspace = true
}
</script>

<template>
  <div class="hero">
    <!-- 背景装饰：渐变光晕 -->
    <div class="hero-glow" aria-hidden="true"></div>

    <div class="hero-mark floating" aria-hidden="true">
      <LogoMark :size="52" />
    </div>

    <h2 class="hero-title animate-in">
      <template v-if="store.pid">今天想把《{{ projectName }}》改成什么？</template>
      <template v-else>从一段原著，开始你的剧本</template>
    </h2>
    <p class="hero-sub animate-in" style="animation-delay: 0.1s">
      <template v-if="store.pid">每个改动都会先给提议：可逐条审阅、可编辑、可回滚。</template>
      <template v-else>导入小说或片段，AI 生成结构化初稿，再逐场对话打磨。</template>
    </p>

    <div class="hero-cards" role="list">
      <button
        v-for="(c, i) in cards"
        :key="c.title"
        class="hero-card animate-in"
        :class="'hue-' + c.hue"
        :style="{ animationDelay: (0.15 + i * 0.06) + 's' }"
        role="listitem"
        @click="onCard(c)"
      >
        <div class="hero-card-glow" aria-hidden="true"></div>
        <svg viewBox="0 0 16 16" class="hero-icon" aria-hidden="true">
          <template v-if="c.icon === 'upload'">
            <path d="M8 10.5V3M5 5.5L8 2.5l3 3M3 10.5v1.7c0 .4.3.8.8.8h8.4c.5 0 .8-.4.8-.8v-1.7" />
          </template>
          <template v-else-if="c.icon === 'doc'">
            <path d="M4.5 2.5h4.2L11.5 5.3v7.2c0 .6-.4 1-1 1H4.5c-.6 0-1-.4-1-1v-9c0-.6.4-1 1-1zM8.7 2.5v2.8h2.8M6.3 8.2h3.4M6.3 10.7h3.4" />
          </template>
          <template v-else-if="c.icon === 'folder'">
            <path d="M2 5.2c0-.7.5-1.2 1.2-1.2h2.4l1.5 1.7h5.7c.7 0 1.2.5 1.2 1.2v5.3c0 .7-.5 1.2-1.2 1.2H3.2c-.7 0-1.2-.5-1.2-1.2V5.2z" />
          </template>
          <template v-else-if="c.icon === 'help'">
            <path d="M14 8A6 6 0 1 1 2 8a6 6 0 0 1 12 0zM6.4 6.3A1.7 1.7 0 1 1 8.6 8c-.4.2-.6.5-.6.9v.2M8 11.4h.01" />
          </template>
          <template v-else-if="c.icon === 'pen'">
            <path d="M3.8 12.2L3 14l1.8-.8 8-8c.5-.5.5-1.3 0-1.8s-1.3-.5-1.8 0l-8 8zM9.8 4.2l2 2" />
          </template>
          <template v-else-if="c.icon === 'bubble'">
            <path d="M13.5 7.6c0 2.5-2.5 4.4-5.5 4.4-.5 0-1-.1-1.5-.2L3 13.5l.7-2.4C2.9 10.3 2.5 9 2.5 7.6c0-2.5 2.5-4.4 5.5-4.4s5.5 1.9 5.5 4.4z" />
          </template>
          <template v-else-if="c.icon === 'pace'">
            <path d="M4.5 3.5L9 8l-4.5 4.5M8.5 3.5L13 8l-4.5 4.5" />
          </template>
          <template v-else-if="c.icon === 'search'">
            <path d="M10.8 10.8L14 14M12.6 7.1a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z" />
          </template>
        </svg>
        <span class="hero-card-title">{{ c.title }}</span>
        <span class="hero-card-desc">{{ c.desc }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.hero {
  min-height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  text-align: center; padding: 40px 12px 48px;
  position: relative; overflow: hidden;
}

/* 背景渐变光晕 */
.hero-glow {
  position: absolute; top: -30%; left: 50%; transform: translateX(-50%);
  width: 600px; height: 400px; pointer-events: none;
  background: radial-gradient(ellipse, color-mix(in oklch, var(--gold) 8%, transparent) 0%, transparent 70%);
  filter: blur(60px);
}

.hero-mark { color: var(--gold); margin-bottom: 20px; position: relative; z-index: 1; }

.hero-title {
  margin: 0; font-size: 22px; font-weight: 700; color: var(--ink);
  letter-spacing: 0.01em; max-width: 36ch; line-height: 1.4; position: relative; z-index: 1;
  background: linear-gradient(135deg, var(--ink) 60%, var(--gold));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.hero-sub {
  margin: 8px 0 0; font-size: 12.5px; color: var(--muted);
  text-wrap: balance; position: relative; z-index: 1;
}

/* 3D 卡片网格 */
.hero-cards {
  margin-top: 30px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px; width: 100%; max-width: 780px; position: relative; z-index: 1;
  perspective: 800px;
}
@media (max-width: 860px) { .hero-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

.hero-card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  padding: 16px 14px 14px; text-align: left; cursor: pointer;
  display: flex; flex-direction: column; align-items: flex-start; gap: 3px;
  color: inherit; font-weight: 400; position: relative; overflow: hidden;
  transition: all 300ms var(--ease);
  transform: perspective(800px) rotateX(0) rotateY(0) translateZ(0);
}
.hero-card:hover {
  background: var(--panel2); border-color: var(--line-strong);
  transform: perspective(800px) rotateX(-2deg) rotateY(1deg) translateZ(10px);
  box-shadow: 0 12px 40px oklch(0 0 0 / 0.35);
}

/* 卡片底部渐变光晕 */
.hero-card-glow {
  position: absolute; bottom: 0; left: 0; right: 0; height: 60%;
  opacity: 0; transition: opacity 300ms var(--ease);
  pointer-events: none;
}
.hero-card:hover .hero-card-glow { opacity: 1; }

/* 不同色调的卡片光晕 */
.hue-gold .hero-card-glow { background: linear-gradient(to top, color-mix(in oklch, var(--gold) 10%, transparent), transparent); }
.hue-gold:hover { border-color: color-mix(in oklch, var(--gold) 30%, var(--line)); }
.hue-gold .hero-icon { stroke: var(--gold); }

.hue-violet .hero-card-glow { background: linear-gradient(to top, color-mix(in oklch, var(--violet) 10%, transparent), transparent); }
.hue-violet:hover { border-color: color-mix(in oklch, var(--violet) 30%, var(--line)); }
.hue-violet .hero-icon { stroke: var(--violet); }

.hue-cyan .hero-card-glow { background: linear-gradient(to top, color-mix(in oklch, var(--cyan) 10%, transparent), transparent); }
.hue-cyan:hover { border-color: color-mix(in oklch, var(--cyan) 30%, var(--line)); }
.hue-cyan .hero-icon { stroke: var(--cyan); }

.hue-rose .hero-card-glow { background: linear-gradient(to top, color-mix(in oklch, var(--rose) 10%, transparent), transparent); }
.hue-rose:hover { border-color: color-mix(in oklch, var(--rose) 30%, var(--line)); }
.hue-rose .hero-icon { stroke: var(--rose); }

.hero-icon {
  width: 18px; height: 18px; margin-bottom: 8px;
  fill: none; stroke-width: 1.4; stroke-linecap: round; stroke-linejoin: round;
  transition: all 300ms var(--ease); position: relative; z-index: 1;
}
.hero-card:hover .hero-icon { transform: scale(1.15); filter: drop-shadow(0 0 6px currentColor); }

.hero-card-title { font-size: 13px; font-weight: 600; color: var(--ink); position: relative; z-index: 1; }
.hero-card-desc { font-size: 11.5px; color: var(--muted); line-height: 1.5; position: relative; z-index: 1; }
</style>
