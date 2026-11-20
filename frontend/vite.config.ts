/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // frontend/.env 의 BACKEND_URL = 백엔드 주소 (첫 화면 스위치가 "진짜 서버"일 때 씀)
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
