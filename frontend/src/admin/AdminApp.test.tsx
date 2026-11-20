import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { AdminApi, AdminOverview, OperationRequest } from '../api'
import { createSim } from '../api/adminMock'
import { AdminApp } from './AdminApp'

const T0 = Date.parse('2026-11-20T07:00:00Z')

/** 가짜 매장을 25분 돌려 둔 API. 조작은 시뮬레이션에 그대로 넘김 */
function setup(path: string, over: Partial<AdminApi> = {}) {
  const sim = createSim({ start: T0, seed: 7, errorsAt: [T0 + 23 * 60_000] })
  sim.runUntil(T0 + 25 * 60_000)
  let push: (o: AdminOverview) => void = () => {}
  const api: AdminApi = {
    getOverview: async () => sim.overview(),
    requestOperation: vi.fn(async (req: OperationRequest) => sim.request(req)),
    getOperation: vi.fn(async (id: string) => {
      sim.step()
      return sim.operation(id)!
    }),
    subscribeOverview(cb, onConnection) {
      push = cb
      onConnection?.(true)
      cb(sim.overview())
      return () => {}
    },
    getEvents: async () => sim.events(T0, sim.now),
    getReplay: async () => sim.frames(T0, sim.now),
    ...over,
  }
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/*" element={<AdminApp api={api} pollMs={0} />} />
      </Routes>
    </MemoryRouter>,
  )
  return { sim, api, refresh: () => act(() => push(sim.overview())) }
}

/** 비상 정지가 아닌 AMR 하나: [robot_id, 화면 이름] */
function movable(sim: ReturnType<typeof createSim>): [string, string] {
  const r = sim.overview().robots.find((x) => x.type === 'AMR' && x.state !== 'E_STOP')!
  return [r.robot_id, `AMR-${r.robot_id.replace(/\D/g, '')}`]
}

describe('A1 통합 관제', () => {
  it('AMR 3대 요약, 목록, 상세가 보이고 목록에서 고르면 상세가 바뀐다', async () => {
    setup('/admin')
    expect(screen.getByText('AMR 3대')).toBeInTheDocument()
    const list = screen.getByRole('complementary', { name: '대상 목록' })
    expect(within(list).getAllByRole('button', { name: /AMR-\d/ })).toHaveLength(3)

    await userEvent.setup().click(within(list).getByRole('button', { name: /AMR-1/ }))
    const detail = screen.getByRole('complementary', { name: '상세' })
    expect(within(detail).getByRole('heading', { name: 'AMR-1' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /매장 지도/ })).toBeInTheDocument()
  })

  it('비상 정지는 확인창을 거쳐 WEB-08로 보내고, WEB-09 결과를 알린다', async () => {
    const { api, sim } = setup('/admin')
    const [id, name] = movable(sim)
    const user = userEvent.setup()
    await user.click(within(screen.getByRole('complementary', { name: '대상 목록' })).getByRole('button', { name: new RegExp(name) }))
    await user.click(screen.getByRole('button', { name: '비상 정지' }))
    const dlg = screen.getByRole('dialog', { name: `${name} 비상 정지` })
    await user.click(within(dlg).getByRole('button', { name: '비상 정지' }))

    expect(api.requestOperation).toHaveBeenCalledWith(expect.objectContaining({ kind: 'E_STOP', target_id: id, request_key: expect.any(String) }))
    expect(await screen.findByRole('status')).toHaveTextContent(`${name} 비상 정지했어요`)
  })

  it('결과를 모르면 다시 눌렀을 때 같은 요청 키로 보낸다', async () => {
    const getOperation = vi.fn(async (id: string) => ({ operation_id: id, status: 'UNKNOWN' as const, message: null }))
    const { api, sim } = setup('/admin', { getOperation })
    const [, name] = movable(sim)
    const user = userEvent.setup()
    await user.click(within(screen.getByRole('complementary', { name: '대상 목록' })).getByRole('button', { name: new RegExp(name) }))
    await user.click(screen.getByRole('button', { name: '일시 중단' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('결과를 확인하지 못했어요')
    await user.click(screen.getByRole('button', { name: '일시 중단' }))

    const calls = vi.mocked(api.requestOperation).mock.calls.map((c) => c[0])
    expect(calls).toHaveLength(2)
    expect(calls[1].request_key).toBe(calls[0].request_key)
  })
})

describe('A2 테이블 · 주문', () => {
  it('정리 대기 테이블은 "정리 완료 → 이용 가능"으로 바로 바꾼다', async () => {
    const { sim, refresh } = setup('/admin/tables')
    // 정리 대기 테이블 하나 만들기
    const busy = sim.overview().tables.find((t) => t.status === 'AVAILABLE')!
    sim.request({ kind: 'SET_TABLE_STATUS', target_id: String(busy.table_id), params: { status: 'CLEANING' }, request_key: 'x' })
    sim.step()
    refresh()

    const card = screen.getByLabelText(`${busy.table_id}번 테이블`)
    expect(within(card).getByText('정리 대기')).toBeInTheDocument()
    await userEvent.setup().click(within(card).getByRole('button', { name: '정리 완료 → 이용 가능' }))
    expect(await screen.findByRole('status')).toHaveTextContent(`${busy.table_id}번 이용 가능으로 바꿨어요`)
    expect(sim.overview().tables.find((t) => t.table_id === busy.table_id)!.status).toBe('AVAILABLE')
  })

  it('손님이 있는 테이블을 비우려 하면 충돌(CONFLICT) 이유를 보여 준다', async () => {
    const { sim } = setup('/admin/tables')
    const used = sim.overview().tables.find((t) => t.status === 'IN_USE')!
    const user = userEvent.setup()
    const card = screen.getByLabelText(`${used.table_id}번 테이블`)
    await user.click(within(card).getByRole('button', { name: '상태 변경' }))
    await user.click(within(card).getByRole('menuitem', { name: '이용 가능으로' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('중복 배정')
  })

  it('주문 목록: 진행 중 / 완료 전환', async () => {
    setup('/admin/tables')
    const panel = screen.getByRole('complementary', { name: '주문 · 조리 현황' })
    await userEvent.setup().click(within(panel).getByRole('button', { name: '완료' }))
    expect(within(panel).getAllByText('완료').length).toBeGreaterThan(1)
  })
})

describe('A3 알람 · 이력', () => {
  it('복구 대기 오류를 고르면 재시도를 보낼 수 있다', async () => {
    const { api, sim } = setup('/admin/alarms')
    expect(await screen.findByRole('heading', { name: /E-ARM-021/ })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: '재시도' }))
    expect(api.requestOperation).toHaveBeenCalledWith(expect.objectContaining({ kind: 'INCIDENT_RETRY' }))
    expect(await screen.findByRole('status')).toHaveTextContent('E-ARM-021 재시도했어요')
    expect(sim.overview().alarms.find((a) => a.code === 'E-ARM-021')!.incident!.result).toBe('RESUME')
  })

  it('경고 탭은 경고만 보여 준다', async () => {
    setup('/admin/alarms')
    await userEvent.setup().click(screen.getByRole('tab', { name: '경고' }))
    const rows = within(screen.getByRole('complementary', { name: '알람 목록' })).getAllByRole('listitem')
    expect(rows.length).toBeGreaterThan(0)
    for (const r of rows) expect(r).toHaveTextContent(/^경고/)
  })

  it('Replay: 조회 결과와 재생 위치가 보인다', async () => {
    setup('/admin/alarms')
    expect(await screen.findByRole('slider', { name: '재생 위치' })).toBeInTheDocument()
    expect(await screen.findByText(/조회 결과 \d+건/)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: '재생' }))
    expect(screen.getByRole('button', { name: '일시정지' })).toBeInTheDocument()
  })
})

function renderOffline(path: string) {
  const api: AdminApi = {
    getOverview: () => Promise.reject(new Error('down')),
    requestOperation: vi.fn(),
    getOperation: vi.fn(),
    subscribeOverview: (_cb, onConnection) => {
      onConnection?.(false)
      return () => {}
    },
    getEvents: () => Promise.reject(new Error('down')),
    getReplay: () => Promise.reject(new Error('down')),
  }
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/*" element={<AdminApp api={api} pollMs={0} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('서버에 연결되지 않을 때', () => {
  it('A1: 매장 구성은 보이고 상태는 연결 안 됨, 무엇을 확인할지 알려 준다', () => {
    renderOffline('/admin')
    expect(screen.getByRole('alert')).toHaveTextContent('백엔드 서버에 연결되지 않았어요')
    expect(screen.getByRole('link', { name: '첫 화면에서 가짜 데이터로 바꾸기' })).toBeInTheDocument()
    expect(screen.getByText('AMR 3대')).toBeInTheDocument()
    const list = screen.getByRole('complementary', { name: '대상 목록' })
    expect(within(list).getAllByText('연결 안 됨')).toHaveLength(3)
    expect(screen.getByRole('button', { name: '비상 정지' })).toBeDisabled()
  })

  it('A2: 테이블 1~6번이 확인 안 됨으로 보이고 상태 변경은 꺼져 있다', () => {
    renderOffline('/admin/tables')
    for (let id = 1; id <= 6; id++) {
      const card = screen.getByLabelText(`${id}번 테이블`)
      expect(within(card).getByText('확인 안 됨')).toBeInTheDocument()
      expect(within(card).getByRole('button', { name: '상태 변경' })).toBeDisabled()
    }
  })
})
