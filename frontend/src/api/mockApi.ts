import {
  ApiError,
  type CreateOrderRequest,
  type CreateVisitRequest,
  type CreateVisitResponse,
  type DiningTable,
  type FrybotApi,
  type GuideProgress,
  type MenuItem,
  type Order,
  type OrderStatus,
  type ServerEvent,
  type TableId,
  type Topic,
  type VisitSnapshot,
} from './contract'
import { TABLES } from './storeLayout'

/** 시안 메뉴. 가격은 DB 제안 단계라 예시 값 */
export const MOCK_MENU: MenuItem[] = [
  { menu_id: 1, name: '치킨', price: 18000, is_available: true },
  { menu_id: 2, name: '볶음밥', price: 9000, is_available: true },
]

export interface MockOptions {
  /** 시뮬레이션 1단계 간격(ms) */
  tickMs?: number
  /** false면 안내 AMR이 모두 바빠 안내 대기(K3)부터 시작 */
  robotAvailable?: boolean
  /** 테이블 태블릿을 열었을 때 빈 테이블이면 손님이 앉은 것으로 만들어 줌 (데모용) */
  autoSeat?: boolean
  /** 정리(CLEANING)가 끝나기까지 단계 수 */
  cleaningTicks?: number
  /** 이미 손님이 있는 테이블 */
  occupied?: TableId[]
  menu?: MenuItem[]
  now?: () => Date
}

/** 인원에 맞는 테이블 고르는 순서: 좌석이 딱 맞는 것, 같으면 입구에서 가까운 것 */
const ASSIGN_ORDER: TableId[] = [5, 6, 1, 2, 4, 3]

type GuideStep = Pick<GuideProgress, 'state' | 'queue_position' | 'eta_sec' | 'progress'>

function guideTimeline(robotAvailable: boolean): GuideStep[] {
  const steps: GuideStep[] = []
  if (!robotAvailable) {
    steps.push({ state: 'PENDING', queue_position: 2, eta_sec: 60, progress: null })
    steps.push({ state: 'PENDING', queue_position: 1, eta_sec: 30, progress: null })
  }
  for (let eta = 30; eta > 0; eta -= 5) {
    steps.push({ state: 'TO_ENTRANCE', queue_position: null, eta_sec: eta, progress: 1 - eta / 30 })
  }
  // 입구에서 안내 시작 → 테이블까지 걷는 동안
  for (let i = 0; i < 12; i++) steps.push({ state: 'GUIDING', queue_position: null, eta_sec: null, progress: null })
  steps.push({ state: 'ARRIVED', queue_position: null, eta_sec: null, progress: null })
  return steps
}

type OrderStep = { status: OrderStatus; readyCount: 'none' | 'first' | 'all'; delivery: Order['delivery_step'] }
const ORDER_STEPS: OrderStep[] = [
  { status: 'ORDERED', readyCount: 'none', delivery: null },
  { status: 'COOKING', readyCount: 'none', delivery: null },
  // 메뉴마다 다른 로봇팔이 동시에 조리 → 먼저 끝난 것부터 서빙 준비 완료 (시안 T3)
  { status: 'COOKING', readyCount: 'first', delivery: null },
  { status: 'READY', readyCount: 'all', delivery: null },
  { status: 'SERVING', readyCount: 'all', delivery: null },
  { status: 'ARRIVED', readyCount: 'all', delivery: 'STOPPED' },
  { status: 'ARRIVED', readyCount: 'all', delivery: 'TRANSFERRING' },
  { status: 'ARRIVED', readyCount: 'all', delivery: 'DONE' },
  { status: 'COMPLETED', readyCount: 'all', delivery: null },
]
const STEP_MIN = 1

interface VisitRec {
  snap: VisitSnapshot
  guideSteps: GuideStep[] | null
  guideAt: number
  orderAt: Map<string, number>
  cleaningLeft: number
}

/** 서버 없이 키오스크·태블릿 흐름을 확인하는 가짜 Web Service */
export function createMockApi(opts: MockOptions = {}): FrybotApi {
  const tickMs = opts.tickMs ?? 1500
  const robotAvailable = opts.robotAvailable ?? true
  const cleaningTicks = opts.cleaningTicks ?? 4
  const menu = opts.menu ?? MOCK_MENU
  const now = opts.now ?? (() => new Date())

  let version = 0
  let visitSeq = 100
  let orderSeq = 11
  let itemSeq = 0
  let queueSeq = 0
  const tables = new Map<TableId, DiningTable>(
    TABLES.map((t) => [
      t.id,
      { table_id: t.id, code: `T${t.id}`, seats: t.seats, status: 'AVAILABLE', visit_id: null },
    ]),
  )
  const visits = new Map<string, VisitRec>()
  const byKey = new Map<string, { body: string; res: unknown }>()
  const subs = new Set<{ topics: Topic[]; cb: (e: ServerEvent) => void }>()
  let timer: ReturnType<typeof setInterval> | null = null

  const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T

  const publishTable = (t: DiningTable) => {
    const e: ServerEvent = { type: 'table', version: ++version, data: clone(t) }
    subs.forEach((s) => s.topics.some((tp) => 'table_id' in tp && tp.table_id === t.table_id) && s.cb(e))
  }
  const publishVisit = (v: VisitRec) => {
    v.snap.version = ++version
    v.snap.can_end =
      (v.snap.status === 'IN_USE' || v.snap.status === 'ASSIGNED') &&
      v.snap.orders.every((o) => o.status === 'COMPLETED' || o.status === 'CANCELED')
    const e: ServerEvent = { type: 'visit', version: v.snap.version, data: clone(v.snap) }
    subs.forEach((s) => s.topics.some((tp) => 'visit_id' in tp && tp.visit_id === v.snap.visit_id) && s.cb(e))
  }

  const setTable = (id: TableId, patch: Partial<DiningTable>) => {
    const t = tables.get(id)!
    Object.assign(t, patch)
    publishTable(t)
  }

  const newVisit = (partySize: number, tableId: TableId | null, seated: boolean): VisitRec => {
    const visit_id = String(++visitSeq)
    const rec: VisitRec = {
      snap: {
        visit_id,
        status: tableId == null ? 'WAITING' : seated ? 'IN_USE' : 'ASSIGNED',
        party_size: partySize,
        table_id: tableId,
        queue_no: tableId == null ? ++queueSeq : null,
        guide: null,
        can_end: false,
        orders: [],
        version: 0,
      },
      guideSteps: tableId != null && !seated ? guideTimeline(robotAvailable) : null,
      guideAt: 0,
      orderAt: new Map(),
      cleaningLeft: 0,
    }
    if (rec.guideSteps) rec.snap.guide = { ...rec.guideSteps[0], robot_id: robotAvailable ? 'pinky1' : null }
    visits.set(visit_id, rec)
    if (tableId != null) setTable(tableId, { status: seated ? 'IN_USE' : 'ASSIGNED', visit_id })
    publishVisit(rec)
    return rec
  }

  const pickTable = (partySize: number) =>
    ASSIGN_ORDER.map((id) => tables.get(id)!)
      .filter((t) => t.status === 'AVAILABLE' && t.seats >= partySize)
      .sort((a, b) => a.seats - b.seats)[0] ?? null

  for (const id of opts.occupied ?? []) {
    const t = tables.get(id)
    if (t) newVisit(t.seats, id, true)
  }

  const eta = (stepsLeft: number) => new Date(now().getTime() + stepsLeft * STEP_MIN * 60_000).toISOString()

  const tick = () => {
    for (const v of visits.values()) {
      let changed = false
      // 안내
      if (v.guideSteps && v.guideAt < v.guideSteps.length - 1) {
        const step = v.guideSteps[++v.guideAt]
        v.snap.guide = { ...step, robot_id: step.state === 'PENDING' ? null : 'pinky1' }
        if (step.state === 'ARRIVED' && v.snap.status === 'ASSIGNED') {
          v.snap.status = 'IN_USE'
          setTable(v.snap.table_id!, { status: 'IN_USE' })
        }
        changed = true
      }
      // 주문 — 서빙 AMR은 한 번에 한 주문만 테이블에 옴
      let robotAtTable = false
      for (const o of v.snap.orders) {
        const at = v.orderAt.get(o.order_id)!
        const next = ORDER_STEPS[at + 1]
        if (!next) continue
        if (next.delivery && robotAtTable) continue
        v.orderAt.set(o.order_id, at + 1)
        o.status = next.status
        o.delivery_step = next.delivery
        const readyAt = now().toISOString()
        o.items.forEach((it, i) => {
          const ready = next.readyCount === 'all' || (next.readyCount === 'first' && i === 0)
          if (ready && !it.ready_at) it.ready_at = readyAt
        })
        o.eta_at = o.status === 'COMPLETED' ? null : eta(ORDER_STEPS.length - 2 - (at + 1))
        if (next.delivery) robotAtTable = true
        changed = true
      }
      // 정리
      if (v.snap.status === 'END_OF_USE' && v.cleaningLeft > 0 && --v.cleaningLeft === 0) {
        const tid = v.snap.table_id!
        setTable(tid, { status: 'AVAILABLE', visit_id: null })
        // 데모: 태블릿이 보고 있는 테이블이면 다음 손님이 바로 앉은 것으로
        const watched = [...subs].some((s) => s.topics.some((tp) => 'table_id' in tp && tp.table_id === tid))
        if (opts.autoSeat && watched) newVisit(tables.get(tid)!.seats, tid, true)
      }
      if (changed) publishVisit(v)
    }
  }

  const ensureTimer = () => {
    if (!timer && subs.size > 0) timer = setInterval(tick, tickMs)
    if (timer && subs.size === 0) {
      clearInterval(timer)
      timer = null
    }
  }

  const idempotent = <T,>(key: string, body: unknown, make: () => T): T => {
    const b = JSON.stringify(body)
    const prev = byKey.get(key)
    if (prev) {
      if (prev.body !== b) throw new ApiError('REQUEST_KEY_CONFLICT', 409)
      return clone(prev.res as T)
    }
    const res = make()
    byKey.set(key, { body: b, res: clone(res) })
    return res
  }

  const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

  return {
    async createVisit(req: CreateVisitRequest): Promise<CreateVisitResponse> {
      await delay(Math.min(300, tickMs))
      if (!Number.isInteger(req.party_size) || req.party_size < 1) throw new ApiError('INVALID_INPUT', 422)
      return idempotent(req.request_key, req, () => {
        const t = pickTable(req.party_size)
        const v = newVisit(req.party_size, t?.table_id ?? null, false)
        return { visit_id: v.snap.visit_id, status: t ? 'ASSIGNED' : 'WAITING', table_id: v.snap.table_id, queue_no: v.snap.queue_no }
      })
    },

    async getVisit(visitId) {
      const v = visits.get(visitId)
      if (!v) throw new ApiError('INVALID_INPUT', 404)
      return clone(v.snap)
    },

    async getMenu() {
      return clone(menu)
    },

    async createOrder(req: CreateOrderRequest) {
      await delay(Math.min(300, tickMs))
      const v = visits.get(req.visit_id)
      if (!v || v.snap.table_id !== req.table_id || v.snap.status === 'END_OF_USE')
        throw new ApiError('INVALID_INPUT', 422)
      const lines = req.items.filter((l) => l.qty > 0)
      if (lines.length === 0) throw new ApiError('INVALID_INPUT', 422)
      return idempotent(req.request_key, req, () => {
        const items = lines.map((l) => {
          const m = menu.find((x) => x.menu_id === l.menu_id)
          if (!m || !m.is_available) throw new ApiError('MENU_UNAVAILABLE', 409)
          return { order_item_id: String(++itemSeq), menu_id: m.menu_id, name: m.name, qty: l.qty, ready_at: null }
        })
        const order: Order = {
          order_id: `ORD-${String(++orderSeq).padStart(4, '0')}`,
          table_id: req.table_id,
          status: 'ORDERED',
          items,
          created_at: now().toISOString(),
          eta_at: eta(ORDER_STEPS.length - 2),
          delivery_step: null,
        }
        v.snap.orders.push(order)
        v.orderAt.set(order.order_id, 0)
        publishVisit(v)
        return { order_id: order.order_id, status: 'ORDERED' as const }
      })
    },

    async endVisit(visitId, requestKey) {
      const v = visits.get(visitId)
      if (!v) throw new ApiError('INVALID_INPUT', 404)
      return idempotent(requestKey, { visitId }, () => {
        if (!v.snap.can_end) return { result: 'PENDING' as const, collect_required: false }
        v.snap.status = 'END_OF_USE'
        v.cleaningLeft = cleaningTicks
        setTable(v.snap.table_id!, { status: 'CLEANING' })
        publishVisit(v)
        return { result: 'ACCEPTED' as const, collect_required: v.snap.orders.length > 0 }
      })
    },

    async getTables() {
      return [...tables.values()].map(clone)
    },

    subscribe(topics, cb) {
      const sub = { topics, cb }
      subs.add(sub)
      for (const tp of topics) {
        if ('table_id' in tp) {
          const t = tables.get(tp.table_id)
          if (!t) continue
          if (opts.autoSeat && t.status === 'AVAILABLE') newVisit(t.seats, t.table_id, true)
          cb({ type: 'table', version: ++version, data: clone(t) })
        } else {
          const v = visits.get(tp.visit_id)
          if (v) cb({ type: 'visit', version: v.snap.version, data: clone(v.snap) })
        }
      }
      ensureTimer()
      return () => {
        subs.delete(sub)
        ensureTimer()
      }
    },

    async callStaff() {
      await delay(Math.min(150, tickMs))
    },
  }
}
