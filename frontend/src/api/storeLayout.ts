/**
 * 매장 배치 (cm, 원점 왼쪽 위, y 아래로).
 * 기준: Confluence "FryBot 매장 맵 구성도"(2026-11-13)와 frybot_control/layout.py — 같은 값을 씁니다.
 */

export const STORE_W = 200
export const STORE_H = 100

export interface TableSpec {
  id: number
  seats: number
  /** 테이블 상판 (x0, y0, x1, y1) */
  rect: [number, number, number, number]
  /** 의자 */
  chairs: [number, number, number, number][]
  /** 안내 AMR이 서는 곳 (가운데 4인석은 위 통로 쪽을 씀) */
  stop: [number, number]
}

const wall = (id: number, x: number, top: boolean): TableSpec => {
  const [y0, y1] = top ? [0, 12] : [88, 100]
  return {
    id,
    seats: 2,
    rect: [x - 6, y0, x + 6, y1],
    chairs: [
      [x - 12, y0, x - 6, y1],
      [x + 6, y0, x + 12, y1],
    ],
    stop: [x > 100 ? x - 3 : x, top ? 23 : 77],
  }
}

const mid = (id: number, x: number, sx: number): TableSpec => ({
  id,
  seats: 4,
  rect: [x - 6, 44, x + 6, 56],
  chairs: [
    [x - 13, 44, x - 6, 50],
    [x - 13, 50, x - 6, 56],
    [x + 6, 44, x + 13, 50],
    [x + 6, 50, x + 13, 56],
  ],
  stop: [sx, 33],
})

/** 번호는 조리 구역에서 가까운 순 */
export const TABLES: TableSpec[] = [
  wall(1, 134, true),
  wall(2, 134, false),
  mid(3, 128, 131),
  mid(4, 74, 74),
  wall(5, 54, true),
  wall(6, 54, false),
]

export const ZONES = {
  charge: [0, 0, 12, 100],
  chargeAisle: [12, 0, 32, 100],
  cook: [166, 0, 200, 100],
} as const

/** 손님 입구 (위쪽 벽, 충전대 앞 통로 위) */
export const ENTRANCE_X = 22
/** 안내 AMR이 손님을 만나는 곳 */
export const GREET: [number, number] = [22, 20]
/** 위·아래 통로 중심선 */
export const AISLE_U = 28
export const AISLE_L = 72

export function tableSpec(id: number) {
  return TABLES.find((t) => t.id === id) ?? null
}

/** 손님 맞이 지점 → 통로 → 테이블 앞 정차 지점 (cm 꼭짓점 목록) */
export function guideRoute(id: number): [number, number][] | null {
  const t = tableSpec(id)
  if (!t) return null
  const [sx, sy] = t.stop
  const aisle = sy < 50 ? AISLE_U : AISLE_L
  return [GREET, [GREET[0], aisle], [sx, aisle], [sx, sy]]
}

/** 화면에 쓰는 테이블 이름: 맵과 같은 "5번" */
export function tableName(id: number | null | undefined) {
  return id == null ? '-' : `${id}번`
}
