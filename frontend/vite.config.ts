import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base：部署子路径（默认 /），生产由后端同源托管构建产物；构建不读取任何课程目录（目录运行时由 GET /api/courses 提供）。
// dev/preview 下 /api（接口与课程目录）和 /course（教材页，后端从 COURSE_DIR 直接提供）代理到本地后端。
// 代理目标：XT_API，未设时 http://127.0.0.1:${XT_PORT ?? PORT ?? 13773}（脚本用 XT_PORT，后端用 PORT）
const api = process.env.XT_API ?? `http://127.0.0.1:${process.env.XT_PORT ?? process.env.PORT ?? 13773}`
const proxy = { '/api': api, '/course': api }

export default defineConfig({
  plugins: [react()],
  base: process.env.XT_BASE ?? '/',
  server: { proxy },
  preview: { proxy },
})
