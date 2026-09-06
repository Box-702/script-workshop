<script setup>
// =====================================================================
// LogoMark.vue —— 品牌图形：场记板 + 剧本行
//
// 「场记板」是剧本工作的行业符号，板身上的两行留白示意剧本正文。
// 线稿风格（stroke 继承 currentColor），单色不抢戏，跟随 DESIGN.md
// 的单色策略：hero 里做安静的徽记，顶栏里做白色圆角 tile 内的反白图形。
// =====================================================================

defineProps({
  size: { type: Number, default: 24 },
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 顶板（打板斜纹） -->
    <rect x="4.5" y="6" width="23" height="6.5" rx="2" />
    <path d="M10.5 7.2l2.4 4.2M17 7.2l2.4 4.2M23.5 7.2l2.4 4.2" />
    <!-- 板身 -->
    <rect x="4.5" y="16.5" width="23" height="10.5" rx="2.6" />
    <!-- 剧本行 -->
    <path d="M9.5 21h13M9.5 24.2h8.5" />
  </svg>
</template>
