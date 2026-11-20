/**
 * 화면이 진짜 백엔드 서버를 쓸지, 목업(가짜) 데이터를 쓸지.
 *   기본 주소 (/kiosk, /table/3, /admin …)        → 진짜 서버 (frontend/.env 의 BACKEND_URL)
 *   /mock 으로 시작하는 주소 (/mock/kiosk …)       → 목업 데이터 (서버 없이 화면 확인용)
 */
export type DataMode = 'mock' | 'server'

export const MOCK_BASE = '/mock'

export function isMockPath(pathname: string) {
  return pathname === MOCK_BASE || pathname.startsWith(`${MOCK_BASE}/`)
}

export function getDataMode(): DataMode {
  if (typeof window === 'undefined') return 'server'
  return isMockPath(window.location.pathname) ? 'mock' : 'server'
}
