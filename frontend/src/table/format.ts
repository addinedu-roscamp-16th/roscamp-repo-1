import type { OrderStatus } from '../api'

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

/** 장바구니 한 줄 — WEB-04 items 항목과 같은 모양 */
export interface CartLine {
  menu_id: number
  qty: number
}

/** T3 단계 표시: 접수 → 조리 중 → 서빙 → 완료 */
export type Stage = 'received' | 'cooking' | 'serving' | 'done'

/** orders.status → T3 단계 */
export function orderStage(status: OrderStatus): Stage {
  switch (status) {
    case 'ORDERED':
    case 'ON_HOLD':
      return 'received'
    case 'COOKING':
    case 'READY':
      return 'cooking'
    case 'SERVING':
    case 'ARRIVED':
      return 'serving'
    case 'COMPLETED':
    case 'CANCELED':
      return 'done'
  }
}

/** T3 메뉴 줄 오른쪽 문구 (시안: 서빙 준비 완료 / 로봇팔이 조리 중) */
export function itemStatusText(status: OrderStatus, ready: boolean): { text: string; accent: boolean } {
  switch (status) {
    case 'ORDERED':
      return { text: '조리 대기', accent: false }
    case 'COOKING':
    case 'READY':
      return ready ? { text: '서빙 준비 완료', accent: true } : { text: '로봇팔이 조리 중', accent: false }
    case 'SERVING':
      return { text: '로봇이 가져가는 중', accent: true }
    case 'ARRIVED':
      return { text: '테이블에 도착', accent: true }
    case 'COMPLETED':
      return { text: '전달 완료', accent: false }
    case 'ON_HOLD':
      return { text: '잠시 멈춤', accent: false }
    case 'CANCELED':
      return { text: '주문 취소', accent: false }
  }
}
