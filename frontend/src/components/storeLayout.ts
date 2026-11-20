/** 매장 배치 좌표 — 시안(K2_table-assigned.html) 기준 */

export const TABLE_W = 76
export const TABLE_H = 52
export const COL_X = [40, 142, 244]
export const ROW_Y = [36, 128]
/** 테이블 사이 세로 통로의 x 좌표 */
const AISLE_X = [129, 231]
export const ENTRANCE = { x: 78, y: 262 }
/** 입구 앞 가로 통로의 y 좌표 */
const FRONT_Y = 220

export const STORE_LAYOUT: { id: string; col: number; row: number }[] = [
  { id: 'T1', col: 0, row: 0 },
  { id: 'T2', col: 1, row: 0 },
  { id: 'T3', col: 2, row: 0 },
  { id: 'T4', col: 0, row: 1 },
  { id: 'T5', col: 1, row: 1 },
  { id: 'T6', col: 2, row: 1 },
]

export function routeTo(tableId: string): string | null {
  const t = STORE_LAYOUT.find((x) => x.id === tableId)
  if (!t) return null
  const cx = COL_X[t.col] + TABLE_W / 2
  const bottom = ROW_Y[t.row] + TABLE_H
  const start = `M${ENTRANCE.x} ${ENTRANCE.y} V${FRONT_Y}`
  if (t.row === ROW_Y.length - 1) {
    // 앞줄: 테이블 바로 앞까지 (시안과 같은 경로)
    return `${start} H${cx} V${bottom + 6}`
  }
  // 뒷줄: 앞줄 테이블을 피해 가까운 통로로 올라간 뒤 테이블 앞으로
  const aisle = AISLE_X.reduce((a, b) => (Math.abs(b - cx) < Math.abs(a - cx) ? b : a))
  const midY = (ROW_Y[t.row] + TABLE_H + ROW_Y[t.row + 1]) / 2
  return `${start} H${aisle} V${midY} H${cx} V${bottom + 6}`
}
