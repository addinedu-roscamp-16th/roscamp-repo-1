import type {
  CartLine,
  Delivery,
  ItemStatus,
  MenuItem,
  Order,
  OrderStage,
  TableApi,
  TableState,
} from './tableTypes'

/** 시안 메뉴 (가격은 예시 값) */
export const MOCK_MENU: MenuItem[] = [
  { menuId: 'chicken', name: '치킨', price: 18000 },
  { menuId: 'friedrice', name: '볶음밥', price: 9000 },
]

export interface MockTableOptions {
  /** 시뮬레이션 1단계 간격(ms) */
  tickMs?: number
  /** 이용 종료 후 테이블이 다시 비는 데 걸리는 단계 수 */
  resetTicks?: number
  /** 지금 시각 (테스트용) */
  now?: () => Date
}

/** 주문 하나가 거치는 단계 — 조리는 메뉴마다 다른 로봇팔이 동시에 진행 */
type Phase = { items: ItemStatus[]; delivery?: Delivery['step'] }
function timeline(n: number): Phase[] {
  const all = (s: ItemStatus) => Array<ItemStatus>(n).fill(s)
  const steps: Phase[] = [{ items: all('queued') }, { items: all('cooking') }]
  // 첫 메뉴가 먼저 완성되는 모습 (시안 T3: 치킨 서빙 준비 완료, 볶음밥 조리 중)
  if (n > 1) steps.push({ items: ['ready', ...all('cooking').slice(1)] })
  steps.push({ items: all('ready') }, { items: all('serving') })
  steps.push({ items: all('serving'), delivery: 'arrived' })
  steps.push({ items: all('serving'), delivery: 'transferring' })
  steps.push({ items: all('served'), delivery: 'done' })
  steps.push({ items: all('served') })
  return steps
}

const STEP_ETA_MIN = 1

function stageOf(items: ItemStatus[]): OrderStage {
  if (items.every((s) => s === 'served')) return 'done'
  if (items.some((s) => s === 'serving')) return 'serving'
  if (items.some((s) => s !== 'queued')) return 'cooking'
  return 'received'
}

/** 서버 없이 T1~T5 흐름을 확인하는 가짜 API */
export function createMockTableApi(opts: MockTableOptions = {}): TableApi {
  const tickMs = opts.tickMs ?? 1500
  const resetTicks = opts.resetTicks ?? 4
  const now = opts.now ?? (() => new Date())
  let seq = 11
  const tables = new Map<
    string,
    {
      session: TableState['session']
      orders: { order: Order; phase: number; steps: Phase[] }[]
      listeners: Set<(s: TableState) => void>
      endedTicks: number
    }
  >()

  const table = (id: string) => {
    let t = tables.get(id)
    if (!t) {
      t = { session: 'active', orders: [], listeners: new Set(), endedTicks: 0 }
      tables.set(id, t)
    }
    return t
  }

  const snapshot = (id: string): TableState => {
    const t = table(id)
    const active = t.orders.find((o) => o.steps[o.phase].delivery)
    return {
      tableId: id,
      session: t.session,
      orders: t.orders.map((o) => o.order),
      delivery: active
        ? {
            orderId: active.order.orderId,
            itemNames: active.order.items.map((i) => i.name),
            step: active.steps[active.phase].delivery!,
          }
        : null,
    }
  }

  const emit = (id: string) => {
    const s = snapshot(id)
    table(id).listeners.forEach((l) => l(s))
  }

  const advance = (id: string) => {
    const t = table(id)
    let changed = false
    if (t.session === 'ended') {
      if (++t.endedTicks >= resetTicks) {
        // 직원이 정리를 마치고 다음 손님이 앉은 것으로 가정
        t.session = 'active'
        t.orders = []
        t.endedTicks = 0
        changed = true
      }
    }
    // 서빙 로봇은 한 번에 한 주문만: 앞 주문 전달이 끝나야 다음 주문이 테이블로 옴
    let robotBusy = false
    for (const o of t.orders) {
      const next = o.steps[o.phase + 1]
      if (!next) continue
      if (next.delivery && robotBusy) continue
      o.phase++
      const items = o.steps[o.phase].items
      o.order = {
        ...o.order,
        items: o.order.items.map((it, i) => ({ ...it, status: items[i] })),
        stage: stageOf(items),
        etaAt:
          stageOf(items) === 'done'
            ? null
            : new Date(now().getTime() + (o.steps.length - 2 - o.phase) * STEP_ETA_MIN * 60_000).toISOString(),
      }
      if (o.steps[o.phase].delivery) robotBusy = true
      changed = true
    }
    if (changed) emit(id)
  }

  return {
    async getMenu() {
      return MOCK_MENU
    },

    async placeOrder(tableId: string, lines: CartLine[]) {
      const t = table(tableId)
      const items = lines
        .filter((l) => l.qty > 0)
        .map((l) => {
          const m = MOCK_MENU.find((x) => x.menuId === l.menuId)
          if (!m) throw new Error(`unknown menu ${l.menuId}`)
          return { menuId: m.menuId, name: m.name, qty: l.qty, status: 'queued' as const }
        })
      if (items.length === 0) throw new Error('empty order')
      const steps = timeline(items.length)
      const order: Order = {
        orderId: `ORD-${String(++seq).padStart(4, '0')}`,
        tableId,
        items,
        stage: 'received',
        placedAt: now().toISOString(),
        etaAt: new Date(now().getTime() + (steps.length - 2) * STEP_ETA_MIN * 60_000).toISOString(),
      }
      t.orders.push({ order, phase: 0, steps })
      emit(tableId)
      return order
    },

    watchTable(tableId, onState) {
      const t = table(tableId)
      t.listeners.add(onState)
      onState(snapshot(tableId))
      const timer = setInterval(() => advance(tableId), tickMs)
      return () => {
        clearInterval(timer)
        t.listeners.delete(onState)
      }
    },

    async endSession(tableId) {
      const t = table(tableId)
      t.session = 'ended'
      t.endedTicks = 0
      emit(tableId)
    },

    async callStaff() {},
  }
}
