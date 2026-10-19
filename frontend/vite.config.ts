import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base：部署子路径（默认 /），生产由 FastAPI 同源托管 dist；dev/preview 下 /api 代理到本地后端
// 代理目标：XT_API，未设时 http://localhost:${XT_PORT ?? PORT ?? 13773}（脚本用 XT_PORT，后端用 PORT）
const api = process.env.XT_API ?? `http://localhost:${process.env.XT_PORT ?? process.env.PORT ?? 13773}`

export default defineConfig({
  plugins: [react()],
  base: process.env.XT_BASE ?? '/',
  server: { proxy: { '/api': api } },
  preview: { proxy: { '/api': api } },
})
