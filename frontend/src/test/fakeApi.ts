import { act } from '@testing-library/react'
import { vi } from 'vitest'
import type { DiningTable, FrybotApi, Order, ServerEvent, Topic, VisitSnapshot } from '../api'
import { MOCK_MENU } from '../api/mockApi'

/** 테스트에서 서버 이벤트를 직접 밀어 넣을 수 있는 가짜 API */
export function fakeApi(over: Partial<FrybotApi> = {}) {
  const subs = new Set<{ topics: Topic[]; cb: (e: ServerEvent) => void }>()
  let version = 0
  const tables = new Map<number, DiningTable>()
  const visits = new Map<string, VisitSnapshot>()

  const emit = (e: ServerEvent) =>
    subs.forEach((s) => {
      const hit = s.topics.some((t) =>
        e.type === 'visit'
          ? 'visit_id' in t && t.visit_id === e.data.visit_id
          : 'table_id' in t && t.table_id === e.data.table_id,
      )
      if (hit) s.cb(e)
    })

  const api: FrybotApi = {
    createVisit: vi.fn(async () => ({ visit_id: 'v1', status: 'ASSIGNED' as const, table_id: 5, queue_no: null })),
    getVisit: vi.fn(async (id: string) => visits.get(id)!),
    getMenu: vi.fn(async () => MOCK_MENU),
    createOrder: vi.fn(async () => ({ order_id: 'ORD-0012', status: 'ORDERED' as const })),
    endVisit: vi.fn(async () => ({ result: 'ACCEPTED' as const, collect_required: true })),
    getTables: vi.fn(async () => [...tables.values()]),
    callStaff: vi.fn(async () => {}),
    subscribe: (topics, cb) => {
      const s = { topics, cb }
      subs.add(s)
      for (const t of topics) {
        if ('table_id' in t && tables.has(t.table_id))
          cb({ type: 'table', version: ++version, data: tables.get(t.table_id)! })
        if ('visit_id' in t && visits.has(t.visit_id))
          cb({ type: 'visit', version: ++version, data: visits.get(t.visit_id)! })
      }
      return () => subs.delete(s)
    },
    ...over,
  }

  return {
    api,
    setTable(t: DiningTable) {
      tables.set(t.table_id, t)
      act(() => emit({ type: 'table', version: ++version, data: t }))
    },
    setVisit(v: VisitSnapshot) {
      visits.set(v.visit_id, v)
      act(() => emit({ type: 'visit', version: ++version, data: v }))
    },
    /** 렌더 전에 초기 상태만 넣기 */
    seed(t: DiningTable, v?: VisitSnapshot) {
      tables.set(t.table_id, t)
      if (v) visits.set(v.visit_id, v)
    },
  }
}

export const visitOf = (over: Partial<VisitSnapshot> = {}): VisitSnapshot => ({
  visit_id: 'v1',
  status: 'IN_USE',
  party_size: 2,
  table_id: 3,
  queue_no: null,
  guide: null,
  can_end: true,
  orders: [],
  version: 1,
  ...over,
})

export const orderOf = (over: Partial<Order> = {}): Order => ({
  order_id: 'ORD-0012',
  table_id: 3,
  status: 'COOKING',
  items: [
    { order_item_id: '1', menu_id: 1, name: '치킨', qty: 1, ready_at: '2026-11-20T07:40:00Z' },
    { order_item_id: '2', menu_id: 2, name: '볶음밥', qty: 1, ready_at: null },
  ],
  created_at: new Date().toISOString(),
  eta_at: new Date(Date.now() + 6 * 60_000).toISOString(),
  delivery_step: null,
  ...over,
})

export const tableOf = (over: Partial<DiningTable> = {}): DiningTable => ({
  table_id: 3,
  code: 'T3',
  seats: 4,
  status: 'IN_USE',
  visit_id: 'v1',
  ...over,
})
