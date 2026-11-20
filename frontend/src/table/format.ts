import type { ItemStatus } from '../api'

/** 18000 → "18,000원" */
export function won(n: number) {
  return `${n.toLocaleString('ko-KR')}원`
}

/** ISO 시각 → "16:48" */
export function clock(iso: string) {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 남은 분 → "약 6분 뒤", 1분 미만이면 "곧 도착" */
export function minutesFromNow(iso: string, now = new Date()) {
  const min = Math.round((new Date(iso).getTime() - now.getTime()) / 60_000)
  return min >= 1 ? `약 ${min}분 뒤` : '곧 도착'
}

/** 받침이 있으면 "이", 없으면 "가" — "치킨이", "피자가" */
export function subjectJosa(word: string) {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  if (code < 0 || code > 11171) return '이(가)'
  return code % 28 === 0 ? '가' : '이'
}

export const ITEM_STATUS_TEXT: Record<ItemStatus, { text: string; accent: boolean }> = {
  queued: { text: '조리 대기', accent: false },
  cooking: { text: '로봇팔이 조리 중', accent: false },
  ready: { text: '서빙 준비 완료', accent: true },
  serving: { text: '로봇이 가져가는 중', accent: true },
  served: { text: '전달 완료', accent: false },
}
