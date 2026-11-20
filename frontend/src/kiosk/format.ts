/** 키오스크에서 고를 수 있는 인원 (5명 이상은 직원 호출) */
export const PARTY_SIZES = [1, 2, 3, 4] as const
export type PartySize = (typeof PARTY_SIZES)[number]

/** 배정 결과를 화면에 보여 줄 때 쓰는 값 */
export interface Seat {
  tableId: number
  seats: number
  partySize: number
}

/** 30 → "약 30초", 90 → "약 2분" */
export function formatEta(sec: number) {
  if (sec < 60) return `약 ${Math.max(1, Math.round(sec))}초`
  return `약 ${Math.round(sec / 60)}분`
}
