/**
 * 화면이 가짜 데이터를 쓸지, 진짜 백엔드 서버에 붙을지.
 * 첫 화면의 스위치로 바꾸고, 기기(브라우저)마다 기억합니다.
 * 진짜 서버 주소는 frontend/.env 의 BACKEND_URL (개발 서버가 /api 를 그쪽으로 넘김).
 */
export type DataMode = 'mock' | 'server'

const KEY = 'oneteam.dataMode'

export function getDataMode(): DataMode {
  try {
    const saved = window.localStorage.getItem(KEY)
    if (saved === 'mock' || saved === 'server') return saved
  } catch {
    /* 저장소를 못 쓰는 브라우저면 기본값 */
  }
  return import.meta.env.VITE_API_MODE === 'http' ? 'server' : 'mock'
}

/** 바꾸면 화면을 새로 불러 새 연결로 시작합니다 */
export function setDataMode(mode: DataMode) {
  try {
    window.localStorage.setItem(KEY, mode)
  } catch {
    /* 저장 못 하면 이번 한 번만 */
  }
  window.location.reload()
}
