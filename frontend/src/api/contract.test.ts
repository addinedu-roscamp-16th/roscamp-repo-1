/**
 * 계약 테스트: 목업이 내는 데이터가 api/openapi.yaml 모양을 지키는지 확인합니다.
 * 목업이 계약과 어긋나면 "목업에서는 되는데 진짜 서버에서는 안 되는" 일이 생기므로, 여기서 먼저 막습니다.
 * (백엔드 쪽 검사는 README의 "계약 테스트" 참고)
 */
import { describe, expect, it } from 'vitest'
import { orderOf, tableOf, visitOf } from '../test/fakeApi'
import { createSim } from './adminMock'
import type { ServerEvent, VisitSnapshot } from './contract'
import { createMockApi } from './mockApi'
import { checkList, checkShape } from './schemaCheck'

const T0 = Date.parse('2026-11-20T07:00:00Z')

describe('계약 테스트: 손님 화면 목업 ↔ openapi.yaml', () => {
  it('메뉴·테이블·접수·방문·주문·종료 응답과 구독 이벤트', async () => {
    const api = createMockApi({ tickMs: 5 })
    expect(checkList('MenuItem', await api.getMenu(3))).toEqual([])
    expect(checkList('DiningTable', await api.getTables())).toEqual([])

    const visit = await api.createVisit({ party_size: 2, request_key: 'k1' })
    expect(checkShape('CreateVisitResponse', visit)).toEqual([])

    const events: ServerEvent[] = []
    const off = api.subscribe([{ visit_id: visit.visit_id }, { table_id: visit.table_id! }], (e) => events.push(e))
    await new Promise((r) => setTimeout(r, 250)) // 안내가 끝나 착석할 때까지
    const seated: VisitSnapshot = await api.getVisit(visit.visit_id)
    expect(checkShape('VisitSnapshot', seated)).toEqual([])

    const order = await api.createOrder({
      visit_id: visit.visit_id,
      table_id: visit.table_id!,
      items: [{ menu_id: 1, qty: 1 }],
      request_key: 'k2',
    })
    expect(checkShape('CreateOrderResponse', order)).toEqual([])
    await new Promise((r) => setTimeout(r, 120))
    expect(checkShape('VisitSnapshot', await api.getVisit(visit.visit_id))).toEqual([])

    off()
    expect(events.length).toBeGreaterThan(3)
    for (const e of events) expect(checkShape('ServerEvent', e)).toEqual([])

    await new Promise((r) => setTimeout(r, 150))
    expect(checkShape('EndVisitResponse', await api.endVisit(visit.visit_id, 'k3'))).toEqual([])
  })

  it('테스트용 가짜 데이터(fakeApi)도 계약을 지킨다', () => {
    expect(checkShape('VisitSnapshot', visitOf({ orders: [orderOf(), orderOf({ status: 'ARRIVED', delivery_step: 'TRANSFERRING' })] }))).toEqual([])
    expect(checkShape('DiningTable', tableOf())).toEqual([])
  })

  it('계약을 어기면 잡아낸다 (검사기 자체 확인)', () => {
    expect(checkShape('MenuItem', { menu_id: 1, name: '치킨', is_available: true })).not.toEqual([]) // price 빠짐
    expect(checkShape('DiningTable', { ...tableOf(), status: 'COLLECTING' })).not.toEqual([]) // 문서에 없는 상태 이름
  })
})

describe('계약 테스트: 관리자 목업 ↔ openapi.yaml', () => {
  const sim = createSim({ start: T0, seed: 7, errorsAt: [T0 + 20 * 60_000] })
  sim.runUntil(T0 + 25 * 60_000)

  it('WEB-07 현황', () => {
    expect(checkShape('AdminOverview', sim.overview())).toEqual([])
  })

  it('WEB-08 조작 요청 · WEB-09 결과 (수락·충돌)', () => {
    const ok = sim.request({ kind: 'PAUSE', target_id: 'pinky3', request_key: 'a' })
    expect(checkShape('OperationAccepted', ok)).toEqual([])
    sim.step()
    expect(checkShape('OperationStatus', sim.operation(ok.operation_id))).toEqual([])
    const conflict = sim.request({ kind: 'SET_TABLE_STATUS', target_id: '1', params: { status: 'IN_USE' }, request_key: 'b' })
    expect(checkShape('OperationAccepted', conflict)).toEqual([])
  })

  it('이력 · Replay', () => {
    expect(checkList('EventLogRow', sim.events(T0, sim.now))).toEqual([])
    expect(checkList('ReplayFrame', sim.frames(T0, sim.now))).toEqual([])
  })
})
