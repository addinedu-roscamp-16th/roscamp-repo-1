import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { createMockKioskApi } from '../api/mockKioskApi'
import type { GuideStatus, KioskApi } from '../api'
import { routeTo } from '../components/storeLayout'
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
    render(<KioskApp api={createMockKioskApi(fast)} />)
    expect(screen.getByRole('heading', { name: '몇 분이 오셨나요?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '인원을 골라 주세요' })).toBeDisabled()
  })

  it('로봇이 있으면 K1 → K2 → K4 (시안처럼 4명 → T5)', async () => {
    render(<KioskApp api={createMockKioskApi(fast)} />)
    await pickAndSubmit(4)

    expect(await screen.findByText('자리를 찾았어요')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /T5 테이블로/ })).toBeInTheDocument()
    expect(screen.getByText('4인석')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /T5 테이블까지/ })).toBeInTheDocument()

    expect(await screen.findByText('로봇이 도착했어요')).toBeInTheDocument()
    expect(screen.getByText('10초 뒤 첫 화면으로 돌아가요')).toBeInTheDocument()
  })

  it('로봇이 없으면 K2 → K3 → K4', async () => {
    render(<KioskApp api={createMockKioskApi({ tickMs: 150, robotAvailable: false })} />)
    await pickAndSubmit(2)

    expect(await screen.findByText('T2 테이블은 맡아 두었어요')).toBeInTheDocument()
    expect(screen.getByText('2번째')).toBeInTheDocument()
    expect(await screen.findByText('1번째')).toBeInTheDocument()
    expect(await screen.findByText('로봇이 도착했어요', {}, { timeout: 3000 })).toBeInTheDocument()
  })

  it('K2에서 "처음으로"를 누르면 배정을 취소하고 K1로 돌아간다', async () => {
    const base = createMockKioskApi({ tickMs: 10_000 })
    const api: KioskApi = { ...base, cancelAssignment: vi.fn(base.cancelAssignment) }
    render(<KioskApp api={api} />)
    const user = await pickAndSubmit(4)

    await screen.findByText('자리를 찾았어요')
    await user.click(screen.getByRole('button', { name: '처음으로' }))

    expect(api.cancelAssignment).toHaveBeenCalledWith('mock-1')
    expect(screen.getByRole('heading', { name: '몇 분이 오셨나요?' })).toBeInTheDocument()
  })

  it('빈 자리가 없으면 K1에 안내 문구를 보여 준다', async () => {
    const all = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6']
    render(<KioskApp api={createMockKioskApi({ ...fast, occupied: all })} />)
    await pickAndSubmit(1)
    expect(await screen.findByRole('alert')).toHaveTextContent('지금은 맞는 자리가 없어요')
  })

  it('K4에서 10초가 지나면 K1로 돌아간다', async () => {
    vi.useFakeTimers()
    try {
      let push: (s: GuideStatus) => void = () => {}
      const base = createMockKioskApi(fast)
      const api: KioskApi = {
        ...base,
        assignTable: async (n) => ({ assignmentId: 'a1', tableId: 'T5', seats: 4, partySize: n }),
        watchGuide: (_id, cb) => {
          push = cb
          return () => {}
        },
      }
      render(<KioskApp api={api} />)
      act(() => screen.getByRole('button', { name: '3명' }).click())
      await act(async () => screen.getByRole('button', { name: '3명으로 자리 찾기' }).click())
      act(() => push({ state: 'robot_arrived', robotId: 'g1' }))
      expect(screen.getByText('로봇이 도착했어요')).toBeInTheDocument()

      for (let i = 0; i < 10; i++) act(() => vi.advanceTimersByTime(1000))
      expect(screen.getByRole('heading', { name: '몇 분이 오셨나요?' })).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('직원 호출을 누르면 알림이 뜬다', async () => {
    render(<KioskApp api={createMockKioskApi(fast)} />)
    await userEvent.setup().click(screen.getByRole('button', { name: '직원 호출' }))
    expect(await screen.findByRole('status')).toHaveTextContent('직원을 불렀어요')
  })
})

describe('매장 배치도 경로', () => {
  it('T5 경로는 시안과 같다', () => {
    expect(routeTo('T5')).toBe('M78 262 V220 H180 V186')
  })
  it('뒷줄 테이블은 통로로 돌아간다', () => {
    expect(routeTo('T2')).toBe('M78 262 V220 H129 V108 H180 V94')
  })
  it('없는 테이블은 null', () => {
    expect(routeTo('T9')).toBeNull()
  })
})
