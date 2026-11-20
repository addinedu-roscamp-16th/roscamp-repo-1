import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { createMockApi } from '../api/mockApi'
import { guideRoute } from '../api/storeLayout'
import { fakeApi, visitOf } from '../test/fakeApi'
import { KioskApp } from './KioskApp'

const fast = { tickMs: 10 }

async function pickAndSubmit(n: number) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: `${n}명` }))
  await user.click(screen.getByRole('button', { name: `${n}명으로 자리 찾기` }))
  return user
}

describe('입구 키오스크 흐름', () => {
  it('K1: 인원을 고르기 전에는 주 버튼이 꺼져 있다', () => {
    render(<KioskApp api={createMockApi(fast)} />)
    expect(screen.getByRole('heading', { name: '몇 분이 오셨나요?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '인원을 골라 주세요' })).toBeDisabled()
  })

  it('로봇이 있으면 K1 → K2 → K4 (2명 → 입구에서 가까운 2인석 5번)', async () => {
    render(<KioskApp api={createMockApi({ tickMs: 40 })} />)
    await pickAndSubmit(2)

    expect(await screen.findByText('자리를 찾았어요')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /5번\s*테이블로/ })).toBeInTheDocument()
    expect(screen.getByText('2인석')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /5번 테이블까지/ })).toBeInTheDocument()

    expect(await screen.findByText('로봇이 도착했어요', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('10초 뒤 첫 화면으로 돌아가요')).toBeInTheDocument()
  })

  it('4명이면 4인석(4번)을 배정한다', async () => {
    render(<KioskApp api={createMockApi({ tickMs: 10_000 })} />)
    await pickAndSubmit(4)
    expect(await screen.findByRole('heading', { name: /4번\s*테이블로/ })).toBeInTheDocument()
    expect(screen.getByText('4인석')).toBeInTheDocument()
  })

  it('안내 로봇이 없으면 K2 → K3 → K4', async () => {
    render(<KioskApp api={createMockApi({ tickMs: 150, robotAvailable: false })} />)
    await pickAndSubmit(2)

    expect(await screen.findByText('5번 테이블은 맡아 두었어요')).toBeInTheDocument()
    expect(screen.getByText('2번째')).toBeInTheDocument()
    expect(await screen.findByText('1번째')).toBeInTheDocument()
    expect(await screen.findByText('로봇이 도착했어요', {}, { timeout: 4000 })).toBeInTheDocument()
  })

  it('접수 요청에 인원과 요청 키를 보내고, 결과 불명이면 같은 키로 다시 보낸다 (WEB-01)', async () => {
    const createVisit = vi
      .fn()
      .mockRejectedValueOnce(new ApiError('RESULT_UNCONFIRMED', 503))
      .mockResolvedValueOnce({ visit_id: 'v1', status: 'ASSIGNED', table_id: 5, queue_no: null })
    const { api } = fakeApi({ createVisit })
    render(<KioskApp api={api} />)
    const user = await pickAndSubmit(2)

    expect(await screen.findByRole('alert')).toHaveTextContent('한 번 더 눌러 주세요')
    await user.click(screen.getByRole('button', { name: '2명으로 자리 찾기' }))
    expect(await screen.findByText('자리를 찾았어요')).toBeInTheDocument()

    const [a, b] = createVisit.mock.calls.map((c) => c[0])
    expect(a.party_size).toBe(2)
    expect(a.request_key).toBeTruthy()
    expect(b.request_key).toBe(a.request_key)
  })

  it('빈 테이블이 없으면(WAITING) 대기 번호를 알려 준다', async () => {
    render(<KioskApp api={createMockApi({ ...fast, occupied: [1, 2, 3, 4, 5, 6] })} />)
    await pickAndSubmit(1)
    expect(await screen.findByRole('alert')).toHaveTextContent('대기 1번으로 접수했어요')
  })

  it('K4에서 10초가 지나면 K1로 돌아간다', async () => {
    vi.useFakeTimers()
    try {
      const f = fakeApi()
      render(<KioskApp api={f.api} />)
      act(() => screen.getByRole('button', { name: '3명' }).click())
      await act(async () => screen.getByRole('button', { name: '3명으로 자리 찾기' }).click())
      f.setVisit(
        visitOf({
          status: 'ASSIGNED',
          table_id: 5,
          guide: { state: 'GUIDING', robot_id: 'pinky1', queue_position: null, eta_sec: null, progress: null },
        }),
      )
      expect(screen.getByText('로봇이 도착했어요')).toBeInTheDocument()

      for (let i = 0; i < 10; i++) act(() => vi.advanceTimersByTime(1000))
      expect(screen.getByRole('heading', { name: '몇 분이 오셨나요?' })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('직원 호출을 누르면 알림이 뜬다', async () => {
    render(<KioskApp api={createMockApi(fast)} />)
    await userEvent.setup().click(screen.getByRole('button', { name: '직원 호출' }))
    expect(await screen.findByRole('status')).toHaveTextContent('직원을 불렀어요')
  })
})

describe('안내 경로 (맵 구성도 좌표)', () => {
  it('벽쪽 테이블: 손님 맞이 → 위 통로 → 테이블 앞', () => {
    expect(guideRoute(5)).toEqual([
      [22, 20],
      [22, 28],
      [54, 28],
      [54, 23],
    ])
  })
  it('아래쪽 테이블은 아래 통로로 간다', () => {
    expect(guideRoute(2)).toEqual([
      [22, 20],
      [22, 72],
      [131, 72],
      [131, 77],
    ])
  })
  it('없는 테이블은 null', () => {
    expect(guideRoute(9)).toBeNull()
  })
})
