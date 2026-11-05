<script setup>
// =====================================================================
// LogoMark.vue —— 「问剧 WENJU」品牌图形 v8（问号 × 播放）
//
// 设计命题：品牌长在「问」字上——问号是「问剧」的根，播放键是「剧」的归宿。
//   - 问号曲线：粗圆端点，映青色，是主笔画
//   - 问号的点：换成金色播放三角——「问出一个故事，然后看它发生」
// 纯平两色，16px 顶栏与 44px 首页都保持清晰（v6 的 3D 挤出、v7 的胶片屏
// 都偏离了「问」字本源，v8 回到问号本体）。
//
// variant:
//   color —— 深底默认：问号 #4E97AE（映青）/ 播放点 #D2A562（灵金）
//   light —— 浅底：问号 #2F7B93 / 播放点 #B08A4E
//   mono  —— 单色：全 currentColor
// =====================================================================
const props = defineProps({
  size: { type: Number, default: 24 },
  variant: { type: String, default: 'color' }, // color | light | mono
})

const PALETTE = {
  color: { q: '#4E97AE', dot: '#D2A562' },
  light: { q: '#2F7B93', dot: '#B08A4E' },
  mono: { q: 'currentColor', dot: 'currentColor' },
}
const c = () => PALETTE[props.variant] || PALETTE.color
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 48 48" fill="none"
    xmlns="http://www.w3.org/2000/svg" aria-hidden="true"
  >
    <!-- 问号主体：起笔左上，钩弧到右侧，垂下收在字的腰线 -->
    <path
      d="M14.5 15.4 C14.5 9.4 19 6.4 24.3 6.4 C30.1 6.4 34.3 9.9 34.3 15.2
         C34.3 20.3 30.2 22 27.3 24.7 C25.5 26.4 24.8 28.2 24.8 30.6"
      :stroke="c().q" stroke-width="5.2" stroke-linecap="round" stroke-linejoin="round"
    />
    <!-- 问号的点 = 播放键：金三角，微圆角 -->
    <path
      d="M21.4 35.8 L29.6 40 L21.4 44.2 Z"
      :fill="c().dot" :stroke="c().dot" stroke-width="2.4" stroke-linejoin="round"
    />
  </svg>
</template>
