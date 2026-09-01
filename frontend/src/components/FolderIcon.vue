<script setup>
// =====================================================================
// FolderIcon.vue —— 可复用的文件夹 SVG（currentColor，随父级着色）
//
// `open` 切换「闭合 / 打开」两种形态；尺寸由外层 CSS 控制。
// 中性单色设计（不占语义色），仅用 currentColor 继承前景，安静不抢戏。
// =====================================================================
defineProps({
  open: { type: Boolean, default: false },
})
</script>

<template>
  <svg class="folder-icon" :class="{ open }" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
    <!-- 闭合 -->
    <path
      v-if="!open"
      d="M1.5 4.25c0-.83.67-1.5 1.5-1.5h2.4c.4 0 .78.16 1.06.44l.66.66c.28.28.66.44 1.06.44h4.88c.83 0 1.5.67 1.5 1.5v6.46c0 .83-.67 1.5-1.5 1.5H3c-.83 0-1.5-.67-1.5-1.5V4.25z"
    />
    <!-- 打开 -->
    <path
      v-else
      d="M1.5 4.25c0-.83.67-1.5 1.5-1.5h2.4c.4 0 .78.16 1.06.44l.66.66c.28.28.66.44 1.06.44h4.88c.83 0 1.5.67 1.5 1.5v.71H4.4a.9.9 0 0 0-.86.66l-2.04 6.07V4.25zm.62 8.08c-.11.33.24.67.58.67h10.7c.29 0 .55-.2.62-.47l1.6-5.6c.09-.32-.25-.93-.59-.93H4.4a.9.9 0 0 0-.86.66l-1.42 5.67z"
    />
  </svg>
</template>

<style scoped>
.folder-icon { width: 16px; height: 16px; flex: none; display: block; }
</style>
