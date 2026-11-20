import { describe, expect, it } from 'vitest'
import type { AmrView } from './adminContract'
import { createSim } from './adminMock'
import { fromMap, roadPath } from './storeLayout'

const T0 = Date.parse('2026-11-20T07:00:00Z')
const MIN = 60_000

function warmed(min = 25, errorsAt: number[] = [T0 + 19 * MIN]) {
  const sim = createSim({ start: T0, seed: 7, errorsAt })
  sim.runUntil(T0 + min * MIN)
  return sim
}
const key = (kind: string, id: string) => `${kind}-${id}-${Math.random()}`

describe('길 찾기', () => {
  it('충전대 → 5번 정차점은 통로 위로만 간다', () => {
    const p = roadPath([6, 20], [54, 23])
    expect(p[0]).toEqual([6, 20])
    expect(p[p.length - 1]).toEqual([54, 23])
    // 꺾이는 곳 말고는 x나 y 한쪽만 바뀜 (테이블을 가로지르지 않음)
    for (let i = 1; i < p.length; i++) expect(p[i][0] === p[i - 1][0] || p[i][1] === p[i - 1][1]).toBe(true)
  })
})

describe('가짜 매장 시뮬레이션', () => {
  it('25분을 돌리면 손님·주문·서빙이 돌아가고 규칙이 지켜진다', () => {
    const sim = warmed()
    const ov = sim.overview()

    // 테이블 하나에 진행 중 손님은 하나 (SR-004)
    for (const t of ov.tables) {
      if (t.status === 'AVAILABLE') expect(t.visit).toBeNull()
      else expect(t.visit).not.toBeNull()
    }
    // 로봇 1대에 진행 중 임무는 1건 (SR-005)
    const active = ov.tasks.filter((t) => !t.finished_at && t.robot_id && t.task_type !== 'COOK')
    expect(new Set(active.map((t) => t.robot_id)).size).toBe(active.length)

    // AMR은 매장 안에 있음
    for (const r of ov.robots.filter((r): r is AmrView => r.type === 'AMR')) {
      const [x, y] = fromMap(r.pose.x, r.pose.y)
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(200)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(100)
    }

    const ev = sim.events(T0, T0 + 25 * MIN)
    expect(ev.filter((e) => e.entity === 'ORDER' && e.to_state === 'COMPLETED').length).toBeGreaterThan(3)
    expect(ev.filter((e) => e.entity === 'VISIT' && e.to_state === 'IN_USE').length).toBeGreaterThan(3)
    expect(sim.frames(T0, T0 + 25 * MIN).length).toBeGreaterThan(1000)
  })

  it('그리퍼 오류가 나면 로봇 비상 정지·주문 보류, 재시도하면 이어서 서빙한다', () => {
    const sim = warmed()
    const al = sim.overview().alarms.find((a) => a.code === 'E-ARM-021')!
    expect(al.incident?.resolved_at).toBeNull()
    const robot = sim.overview().robots.find((r) => r.robot_id === al.source)!
    expect(robot.state).toBe('E_STOP')
    const orderId = al.incident!.order_id!
    expect(sim.overview().orders.find((o) => o.order_id === orderId)!.status).toBe('ON_HOLD')

    const op = sim.request({ kind: 'INCIDENT_RETRY', target_id: al.alarm_id, request_key: key('r', al.alarm_id) })
    expect(op.result).toBe('ACCEPTED')
    sim.step()
    expect(sim.operation(op.operation_id)?.status).toBe('SUCCEEDED')
    expect(sim.overview().robots.find((r) => r.robot_id === al.source)!.state).toBe('DOCKED')
    expect(sim.overview().alarms.find((a) => a.alarm_id === al.alarm_id)!.incident!.result).toBe('RESUME')

    sim.runUntil(sim.now + 3 * MIN)
    const ev = sim.events(T0, sim.now)
    expect(ev.some((e) => e.entity === 'ORDER' && e.entity_id === orderId && e.to_state === 'COMPLETED')).toBe(true)
  })

  it('작업 취소를 고르면 임무·주문이 취소되고 로봇은 복귀한다', () => {
    const sim = warmed()
    const al = sim.overview().alarms.find((a) => a.code === 'E-ARM-021')!
    const op = sim.request({ kind: 'INCIDENT_STOP', target_id: al.alarm_id, request_key: key('s', al.alarm_id) })
    sim.step()
    expect(sim.operation(op.operation_id)?.status).toBe('SUCCEEDED')
    const ov = sim.overview()
    expect(ov.orders.find((o) => o.order_id === al.incident!.order_id)?.status).toBe('CANCELED')
    expect(ov.robots.find((r) => r.robot_id === al.source)!.state).toBe('RETURNING')
  })

  it('정리 대기 테이블만 이용 가능으로 바꿀 수 있다 (중복 배정 방지)', () => {
    const sim = warmed(10, [])
    const busy = sim.overview().tables.find((t) => t.status === 'IN_USE' || t.status === 'ASSIGNED')!
    const r = sim.request({
      kind: 'SET_TABLE_STATUS',
      target_id: String(busy.table_id),
      params: { status: 'AVAILABLE' },
      request_key: key('t', '1'),
    })
    expect(r.result).toBe('CONFLICT')
    expect(r.reason).toContain('중복 배정')
  })

  it('같은 요청 키는 한 번만 처리한다', () => {
    const sim = warmed(5, [])
    const req = { kind: 'PAUSE' as const, target_id: 'pinky1', request_key: 'same' }
    const a = sim.request(req)
    const b = sim.request(req)
    expect(b.operation_id).toBe(a.operation_id)
  })

  it('비상 정지 → 알람 생성, 일시 중단 → 재개', () => {
    const sim = warmed(5, [])
    sim.request({ kind: 'E_STOP', target_id: 'pinky2', request_key: 'e' })
    sim.step()
    const ov = sim.overview()
    expect(ov.robots.find((r) => r.robot_id === 'pinky2')!.state).toBe('E_STOP')
    expect(ov.alarms[0]).toMatchObject({ level: 'ERROR', source: 'pinky2', code: 'E-STOP-00' })

    sim.request({ kind: 'PAUSE', target_id: 'pinky1', request_key: 'p' })
    sim.step()
    expect(sim.overview().robots.find((r) => r.robot_id === 'pinky1')!.state).toBe('PAUSED')
    sim.request({ kind: 'RESUME', target_id: 'pinky1', request_key: 'q' })
    sim.step()
    expect(sim.overview().robots.find((r) => r.robot_id === 'pinky1')!.state).not.toBe('PAUSED')
  })
})
