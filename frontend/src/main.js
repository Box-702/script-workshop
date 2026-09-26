// =====================================================================
// main.js —— 应用入口
//
// 职责：
//   - 创建 Vue 应用实例并挂载到 #app；
//   - 引入全局样式（设计变量 + 基础控件样式）。
// =====================================================================

import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
// 楷书 UI 字体（本地打包，不依赖外网）：霞鹜文楷（LXGW WenKai），
// 用于侧边栏 / 面板 / 输入栏等周边框架；AI 对话区与品牌字标保持现代无衬线。
import 'lxgw-wenkai-webfont/lxgwwenkai-regular.css'
import 'lxgw-wenkai-webfont/lxgwwenkai-bold.css'

createApp(App).mount('#app')
