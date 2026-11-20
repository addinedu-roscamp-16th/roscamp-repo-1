/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // npm run dev:server 이면 .env.server 를 읽음. BACKEND_URL 로 백엔드 주소를 바꿀 수 있음
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [react()],
    server: {
      host: true, // 같은 네트워크의 태블릿에서 접속 가능하도록
      proxy: {
        // 화면의 /api 요청을 백엔드(FastAPI)로 넘깁니다. WebSocket(/api/ws)도 함께.
        '/api': { target: env.BACKEND_URL || 'http://localhost:8000', ws: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: { modules: { classNameStrategy: 'non-scoped' } },
    },
  }
})
