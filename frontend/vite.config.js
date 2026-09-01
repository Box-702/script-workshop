// =====================================================================
// vite.config.js —— Vite 构建配置
//
// 职责：
//   - 启用 Vue 3 单文件组件支持；
//   - 开发模式下把 /api 请求代理到 FastAPI 后端（默认 8000 端口），
//     前端跑 `npm run dev` 即可联调，无需处理跨域；
//   - 构建产物输出到 dist/，由 FastAPI 在生产环境直接托管。
// =====================================================================

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
