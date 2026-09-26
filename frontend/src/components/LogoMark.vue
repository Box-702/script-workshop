<script setup>
// =====================================================================
// LogoMark.vue —— 「映叙 YINGXU」品牌图形 v6（3D 立体版）
//
// 图形语言：一块立起来的 5:8 玻璃剧集屏（2.5D 挤出——深色玻璃面板 +
// 右下侧板，flat 分面着色不用渐变）+ 一条真正绕过去的胶片剪辑带
// （正面带齿孔；拐过右边缘时在侧板上留一段压暗的转折，然后消失在
// 背后——物理上正确的环绕）；屏内一颗灵感金点带微光。
// 让故事长出画面。
//
// v6 相对 v5：加立体——玻璃面板、挤出侧板、带子在侧板上的转折面、
// 光点微光。几何与降饱和色板延续。
//
// variant:
//   color —— 深底默认：映青框 #4E97AE / 玻璃 #0F1822 / 侧板 #1F4E5F /
//            带 #C6D0DA / 带转折 #8FA3B0 / 灵金点 #D2A562
//   light —— 浅底：框 #2F7B93 / 玻璃 #F2F7FA / 侧板 #1D5D73 /
//            带 #2B3844 / 转折 #5E7887 / 点 #B08A4E
//   mono  —— 单色：全 currentColor（侧板 30%、转折 55%、玻璃透明）
// =====================================================================
const props = defineProps({
  size: { type: Number, default: 24 },
  variant: { type: String, default: 'color' }, // color | light | mono
})

const PALETTE = {
  color: {
    frame: '#4E97AE', band: '#C6D0DA', dot: '#D2A562',
    plate: '#1F4E5F', glass: '#0F1822', wrap: '#8FA3B0', halo: '#D2A562',
  },
  light: {
    frame: '#2F7B93', band: '#2B3844', dot: '#B08A4E',
    plate: '#1D5D73', glass: '#F2F7FA', wrap: '#5E7887', halo: '#B08A4E',
  },
  mono: {
    frame: 'currentColor', band: 'currentColor', dot: 'currentColor',
    plate: 'currentColor', glass: 'transparent', wrap: 'currentColor', halo: 'currentColor',
  },
}
// 模板里以 c().xxx 取色；保持普通函数（computed 在模板中会被解包，不能当函数调用）
const c = () => PALETTE[props.variant] || PALETTE.color
const isMono = () => props.variant === 'mono'

// 多实例各自的 mask / clip id（同页多个 Logo 不能共用 id）
const uid = Math.random().toString(36).slice(2, 9)
const maskId = `yx-film-${uid}`
const clipId = `yx-glass-${uid}`

// 齿孔：带身两侧各 11 孔（局部坐标，随带身一起旋转）
const holeXs = [3, 7.1, 11.2, 15.3, 19.4, 23.5, 27.6, 31.7, 35.8, 39.9, 44]
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 48 48" fill="none"
    xmlns="http://www.w3.org/2000/svg" aria-hidden="true"
  >
    <defs>
      <!-- 齿孔镂空：黑 = 透明孔 -->
      <mask :id="maskId" maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48">
        <rect x="1" y="21" width="46" height="9.5" rx="2" fill="#fff" />
        <rect
          v-for="(hx, i) in holeXs" :key="'t' + i"
          :x="hx" y="22.4" width="2.4" height="1.5" rx="0.4" fill="#000"
        />
        <rect
          v-for="(hx, i) in holeXs" :key="'b' + i"
          :x="hx" y="27.5" width="2.4" height="1.5" rx="0.4" fill="#000"
        />
      </mask>
      <!-- 玻璃面板裁剪：带子只出现在正面玻璃上 -->
      <clipPath :id="clipId">
        <rect x="14" y="8" width="20" height="32" rx="6" />
      </clipPath>
    </defs>

    <!-- 挤出侧板：后方偏移的背板（右、下露出 = 厚度） -->
    <rect
      x="18.5" y="11.5" width="20" height="32" rx="6"
      :fill="c().plate" :opacity="isMono() ? 0.3 : 1"
    />
    <!-- 剪辑带在侧板上的转折面：拐过右边缘、压暗、消失于背后 -->
    <path
      d="M34 18.4 L38.5 15.9 L38.5 22.1 L34 24.6 Z"
      :fill="c().wrap" :opacity="isMono() ? 0.55 : 1"
    />
    <!-- 玻璃面板（正面） -->
    <rect x="14" y="8" width="20" height="32" rx="6" :fill="c().glass" />
    <!-- 胶片剪辑带：正面段（齿孔镂空），左右两端被玻璃边缘裁掉 = 绕到背后 -->
    <g transform="rotate(-29 24 24)" :clip-path="`url(#${clipId})`">
      <rect
        x="1" y="21" width="46" height="9.5" rx="2"
        :fill="c().band" :mask="`url(#${maskId})`"
      />
    </g>
    <!-- 屏框：右上开口，压在带子与玻璃之上 -->
    <path
      d="M22 8 H20 Q14 8 14 14 V34 Q14 40 20 40 H28 Q34 40 34 34 V14"
      :stroke="c().frame" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round"
    />
    <!-- 灵感光点：微光 + 本体 -->
    <circle cx="24" cy="14.5" r="6" :fill="c().halo" opacity="0.16" />
    <circle cx="24" cy="14.5" r="2.6" :fill="c().dot" />
  </svg>
</template>
