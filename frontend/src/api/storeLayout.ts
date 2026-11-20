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

/* ── 관리자 지도(A1·A3)용: frybot_control/layout.py 와 같은 값 ── */

export type Pt = [number, number]
type Box = readonly [number, number, number, number]

/** 충전대 (CH1~CH3) 칸과, AMR이 서는 점 */
export const CHARGERS: { id: string; rect: Box; dock: Pt }[] = [
  { id: 'CH1', rect: [0, 13, 12, 27], dock: [6, 20] },
  { id: 'CH2', rect: [0, 43, 12, 57], dock: [6, 50] },
  { id: 'CH3', rect: [0, 73, 12, 87], dock: [6, 80] },
]
/** 음식 받는 곳: 튀김(위), 웍(아래) */
export const PICKUPS = { FRY: [183, AISLE_U] as Pt, WOK: [183, AISLE_L] as Pt }
/** 비켜 서는 곳(벽쪽 테이블 사이)과 조리 구역 옆 대기 칸 */
export const BAYS: Box[] = [
  [72, 1, 116, 11],
  [72, 89, 116, 99],
]
export const STANDBY: Box[] = [
  [150, 1, 164, 11],
  [150, 89, 164, 99],
]
/** 조리 로봇팔은 벽 밖 조리대에 있음 */
export const COOK_ARMS = { FRY: [214, AISLE_U] as Pt, WOK: [214, AISLE_L] as Pt }

/** AMR id(pinky1~3)의 집(충전대) */
export function homeOf(robotId: string): Pt {
  const i = Math.max(0, Number(robotId.replace(/\D/g, '')) - 1)
  return CHARGERS[i % CHARGERS.length].dock
}

/** 지도 좌표(m, y 위쪽) ↔ 매장 좌표(cm, y 아래쪽) */
export const toMap = ([x, y]: Pt): Pt => [x / 100, (STORE_H - y) / 100]
export const fromMap = (x: number, y: number): Pt => [x * 100, STORE_H - y * 100]

/** 통로 중심선을 따라가는 길 그래프 (layout.py build_roadmap 과 같은 모양, 가운데 테이블은 위쪽 정차점만) */
function buildRoadmap() {
  const key = ([x, y]: Pt) => `${x}_${y}`
  const nodes = new Map<string, Pt>()
  const adj = new Map<string, string[]>()
  const link = (a: Pt, b: Pt) => {
    for (const p of [a, b]) {
      if (nodes.has(key(p))) continue
      nodes.set(key(p), p)
      adj.set(key(p), [])
    }
    adj.get(key(a))!.push(key(b))
    adj.get(key(b))!.push(key(a))
  }
  const line = (pts: Pt[]) => pts.slice(1).forEach((p, i) => link(pts[i], p))
  const U = AISLE_U
  const L = AISLE_L
  const GAP_R = 153
  const xs = [22, 38, 54, 74, 88, 101, 114, 131, GAP_R, 166, 183]
  line(xs.map((x) => [x, U]))
  line(xs.map((x) => [x, L]))
  line([20, U, 50, L, 80, 92].map((y) => [22, y]))
  for (const x of [38, 101, GAP_R]) line([[x, U], [x, 50], [x, L]])
  line([[22, 50], [38, 50]])
  line([[GAP_R, 50], [166, 50], [183, 50]])
  line([8, U, 50, L, 92].map((y) => [183, y]))
  line([[88, U], [88, 6], [114, 6], [114, U]])
  line([[88, L], [88, 94], [114, 94], [114, L]])
  line([[GAP_R, U], [157, 6]])
  line([[GAP_R, L], [157, 94]])
  for (const t of TABLES) line([[t.stop[0], t.stop[1] < 50 ? U : L], t.stop])
  for (const c of CHARGERS) line([c.dock, [22, c.dock[1]]])
  return { nodes, adj, key }
}
const ROADMAP = buildRoadmap()

/** 두 점 사이 길(cm 꼭짓점). 출발·도착은 가장 가까운 길 위 점으로 붙임 */
export function roadPath(from: Pt, to: Pt): Pt[] {
  const { nodes, adj, key } = ROADMAP
  const near = (p: Pt) => {
    let best = ''
    let bd = Infinity
    for (const [k, n] of nodes) {
      const d = Math.hypot(n[0] - p[0], n[1] - p[1])
      if (d < bd) {
        bd = d
        best = k
      }
    }
    return best
  }
  const s = near(from)
  const g = near(to)
  const dist = new Map([[s, 0]])
  const prev = new Map<string, string>()
  const open = new Set([s])
  while (open.size) {
    let u = ''
    let ud = Infinity
    for (const k of open) {
      if (dist.get(k)! < ud) {
        ud = dist.get(k)!
        u = k
      }
    }
    open.delete(u)
    if (u === g) break
    const [ux, uy] = nodes.get(u)!
    for (const v of adj.get(u)!) {
      const [vx, vy] = nodes.get(v)!
      const nd = ud + Math.hypot(vx - ux, vy - uy)
      if (nd >= (dist.get(v) ?? Infinity)) continue
      dist.set(v, nd)
      prev.set(v, u)
      open.add(v)
    }
  }
  const out: Pt[] = []
  for (let k: string | undefined = g; k; k = prev.get(k)) out.unshift(nodes.get(k)!)
  if (out[0] && key(out[0]) !== key(from)) out.unshift(from)
  if (key(out[out.length - 1]) !== key(to)) out.push(to)
  return out
}
