import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify('1.0.0'),
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 7999,
    // R1 遗留缺口（2026-08-10 验收准备修复）：dev 模式 /api 请求（REST + WS）转发到后端
    // 链路：浏览器 7999 → Vite proxy → 宿主机 18001（docker-compose 映射）→ 容器内 8001
    proxy: {
      '/api': {
        target: 'http://localhost:18001',
        changeOrigin: true,
        ws: true, // /api/webui/ws 的 WebSocket 也走代理
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    exclude: ['**/dist/**', '**/node_modules/**'],
    // agent reporter（vitest 4.1——WB 调研建议 3）：AI 协作时最小化输出
    // （检测 AI 代理自动精简 terminal 输出——coding agent 调试友好）
    reporter: ['default', 'agent'],
  },
})