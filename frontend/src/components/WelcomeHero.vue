<script setup>
// =====================================================================
// WelcomeHero.vue —— 对话区空态：品牌徽记 + 引导标语 + 建议卡片
//
// 形制参考 Codex / DeepSeek 的开始页：居中安静的徽记，一句「把当前项目
// 变成问题」的标语，下面一组可点击的建议卡片。点击卡片不是直接发送，
// 而是把文本填进下方输入框（由用户确认后发送），与 Codex 的交互一致；
// 「新建剧本 / 工作目录」这类导航型卡片则直接打开对应弹窗。
//
// 两种模式随 store.pid 自适应：
//   - 未选项目：卡片引导「导入原著」（创建项目是第一件事）；
//   - 已选项目：标语带上剧名，卡片是具体改编动作。
// =====================================================================

import { computed } from 'vue'
import { store } from '../stores/app'
import LogoMark from './LogoMark.vue'

const projectName = computed(
  () => store.projects.find((p) => p.id === store.pid)?.title || ''
)

/** 填进输入框（draftSeq 触发 ChatComposer 关注并聚焦）。 */
function fill(text) {
  store.draft = text
  store.draftSeq++
}

// 卡片定义：icon = 线稿图形名；fill 有值填输入框，否则 open 指定弹窗。
const CREATE_CARDS = [
  { icon: 'upload', title: '上传原著文件', desc: '.txt / .md / .docx，导入即建知识库', open: 'newProject' },
  { icon: 'doc', title: '粘贴文本开始', desc: '复制一段小说，也能直接生成初稿', open: 'newProject' },
  { icon: 'folder', title: '设置工作目录', desc: '剧本以真实文件落盘，随时打开', open: 'workspace' },
  { icon: 'help', title: '它能做什么？', desc: '问问 Agent 的工作方式与边界', fill: '你能帮我做什么？' },
]

const PROJECT_CARDS = [
  { icon: 'pen', title: '生成初稿', desc: '从原著产出结构化剧本', fill: '生成初稿' },
  { icon: 'bubble', title: '打磨对白', desc: '把对白改得更口语、更像人说话', fill: '把对白改口语一点' },
  { icon: 'pace', title: '调整节奏', desc: '节奏改紧凑一点，保留原结构', fill: '节奏改紧凑一点' },
  { icon: 'search', title: '检索项目知识', desc: '同类剧的走向、手法与作者风格', fill: '这类悬疑剧怎么设计反转？' },
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
    <div class="hero-mark" aria-hidden="true">
      <LogoMark :size="46" />
    </div>

    <h2 class="hero-title">
      <template v-if="store.pid">今天想把《{{ projectName }}》改成什么？</template>
      <template v-else>从一段原著，开始你的剧本</template>
    </h2>
    <p class="hero-sub">
      <template v-if="store.pid">每个改动都会先给提议：可逐条审阅、可编辑、可回滚。</template>
      <template v-else>导入小说或片段，AI 生成结构化初稿，再逐场对话打磨。</template>
    </p>

    <div class="hero-cards" role="list">
      <button
        v-for="c in cards"
        :key="c.title"
        class="hero-card"
        role="listitem"
        @click="onCard(c)"
      >
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
  min-height: 100%;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  text-align: center;
  padding: 40px 12px 48px;
}

/* 徽记：安静的线稿，不铺底色（Codex 式 ghost glyph） */
.hero-mark { color: var(--dim); margin-bottom: 20px; }

.hero-title {
  margin: 0; font-size: 20px; font-weight: 700; color: var(--ink);
  letter-spacing: 0.01em; max-width: 36ch; line-height: 1.4;
}
.hero-sub {
  margin: 8px 0 0; font-size: 12.5px; color: var(--muted);
  text-wrap: balance;
}

/* 建议卡片：--panel 底 + 1px 边，hover 亮一层；左对齐的图标 + 两行文案 */
.hero-cards {
  margin-top: 30px;
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px; width: 100%; max-width: 780px;
}
@media (max-width: 860px) { .hero-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

.hero-card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  padding: 14px 14px 12px; text-align: left; cursor: pointer;
  display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  color: inherit; font-weight: 400;
  transition: background-color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}
.hero-card:hover {
  background: var(--panel2);
  border-color: var(--line-strong);
}
.hero-card:active { background: color-mix(in oklch, var(--ink) 7%, var(--panel)); }

.hero-icon {
  width: 16px; height: 16px; margin-bottom: 8px;
  fill: none; stroke: var(--muted); stroke-width: 1.4;
  stroke-linecap: round; stroke-linejoin: round;
  transition: color var(--dur) var(--ease);
}
.hero-card:hover .hero-icon { stroke: var(--ink); }

.hero-card-title { font-size: 13px; font-weight: 600; color: var(--ink); }
.hero-card-desc { font-size: 11.5px; color: var(--muted); line-height: 1.5; }
</style>
