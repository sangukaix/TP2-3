import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    // TP2-3 기본 개발 포트는 8100·8111입니다. 배포에서는 Nginx가 /api와 /ai를 라우팅합니다.
    server: {
      proxy: {
        '/api': {
          target: env.VITE_BACKEND_PROXY_TARGET || 'http://127.0.0.1:8100',
          changeOrigin: true,
        },
        '/ai': {
          target: env.VITE_AI_PROXY_TARGET || 'http://127.0.0.1:8111',
          changeOrigin: true,
        },
      },
    },
  }
})
