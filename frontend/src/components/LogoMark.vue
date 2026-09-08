<script setup>
// =====================================================================
// LogoMark.vue —— 剧本工坊品牌图标
//
// 设计：场记板 + 钢笔尖 + 星芒灵感。
// 金色渐变，带微光 glow 效果。单色模式下回退为 currentColor。
// =====================================================================
defineProps({ size: { type: Number, default: 24 } })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="lg" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="#F5C542" />
        <stop offset="100%" stop-color="#D4882A" />
      </linearGradient>
      <filter id="gl"><feGaussianBlur stdDeviation="1.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <!-- 场记板外框 -->
    <rect x="8" y="18" width="48" height="38" rx="6" stroke="url(#lg)" stroke-width="2.5" fill="none" />
    <!-- 顶板横条 -->
    <path d="M8 26h48" stroke="url(#lg)" stroke-width="2.5" stroke-linecap="round" />
    <!-- 斜纹 -->
    <path d="M16 18v8M26 18v8M36 18v8M46 18v8" stroke="url(#lg)" stroke-width="1.8" stroke-linecap="round" opacity="0.5" />
    <!-- 钢笔尖 -->
    <path d="M32 30l-7 16h5l2-6 2 6h5z" fill="url(#lg)" filter="url(#gl)" />
    <!-- 笔尖高光 -->
    <path d="M32 30l-2.5 7h5z" fill="#FFF3D0" opacity="0.4" />
    <!-- 星芒 -->
    <circle cx="19" cy="42" r="1.8" fill="url(#lg)" opacity="0.45" />
    <circle cx="45" cy="42" r="1.8" fill="url(#lg)" opacity="0.45" />
    <path d="M32 10l2 5h-4z" fill="#F5C542" opacity="0.6" />
  </svg>
</template>
