<script setup>
// =====================================================================
// FolderIcon.vue —— 文件夹图标（v2，对齐全站 AppIcon 描边语言）
//
// `open` 切换「闭合 / 打开」两种形态；尺寸由外层 CSS 控制。
// currentColor 继承前景，安静不抢戏。
// =====================================================================
defineProps({
  open: { type: Boolean, default: false },
})
</script>

<template>
  <svg
    class="folder-icon" viewBox="0 0 16 16" aria-hidden="true"
    fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
  >
    <!-- 闭合：文件夹轮廓 + 折页线索 -->
    <path v-if="!open" d="M1.7 4.4c0-.55.45-1 1-1h2.3c.3 0 .58.13.77.36l.55.64h5.48c.55 0 1 .45 1 1v6c0 .55-.45 1-1 1H2.7c-.55 0-1-.45-1-1v-7z" />
    <!-- 打开：抽屉式打开形态 -->
    <template v-else>
      <path d="M1.7 4.4c0-.55.45-1 1-1h2.3c.3 0 .58.13.77.36l.55.64h5.48c.55 0 1 .45 1 1v1.1H4.1c-.42 0-.79.26-.93.66L1.7 11.5v-7.1z" />
      <path d="M4.1 7.1h10.1l-1.3 4.3c-.13.42-.52.7-.96.7H3.2c-.55 0-1-.45-1-1 0-.12.02-.23.06-.34L3.7 7.76c.14-.4.51-.66.93-.66z" />
    </template>
  </svg>
</template>

<style scoped>
.folder-icon { width: 16px; height: 16px; flex: none; display: block; }
</style>
