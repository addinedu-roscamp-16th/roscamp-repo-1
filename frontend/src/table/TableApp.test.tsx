import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { CartLine, Order, TableApi, TableState } from '../api'
import { MOCK_MENU, createMockTableApi } from '../api/mockTableApi'
import { minutesFromNow, subjectJosa, won } from './format'
import { TableApp } from './TableApp'

/** 테스트에서 상태를 직접 밀어 넣을 수 있는 API */
function controlledApi(initial: Order[] = []) {
  let push: (s: TableState) => void = () => {}
  const api: TableApi = {
    getMenu: async () => MOCK_MENU,
    placeOrder: vi.fn(async (tableId: string, lines: CartLine[]) => {
      const o: Order = {
        orderId: 'ORD-0012',
        tableId,
        items: lines.map((l) => ({
          menuId: l.menuId,
          name: MOCK_MENU.find((m) => m.menuId === l.menuId)!.name,
          qty: l.qty,
          status: 'queued' as const,
        })),
        stage: 'received',
        placedAt: new Date().toISOString(),
        etaAt: new Date(Date.now() + 6 * 60_000).toISOString(),
      }
      push({ tableId, session: 'active', orders: [o], delivery: null })
      return o
    }),
    watchTable: (_id, cb) => {
      push = cb
      cb({ tableId: 'T3', session: 'active', orders: initial, delivery: null })
      return () => {}
    },
    endSession: vi.fn(async () => {
      push({ tableId: 'T3', session: 'ended', orders: [], delivery: null })
    }),
    callStaff: vi.fn(async () => {}),
  }
  return { api, push: (s: TableState) => act(() => push(s)) }
}

const order = (over: Partial<Order> = {}): Order => ({
  orderId: 'ORD-0012',
  tableId: 'T3',
  items: [
    { menuId: 'chicken', name: '치킨', qty: 1, status: 'ready' },
    { menuId: 'friedrice', name: '볶음밥', qty: 1, status: 'cooking' },
  ],
  stage: 'cooking',
  placedAt: new Date().toISOString(),
  etaAt: new Date(Date.now() + 6 * 60_000).toISOString(),
  ...over,
})

async function orderChickenAndRice(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '치킨 더하기' }))
  await user.click(screen.getByRole('button', { name: '볶음밥 더하기' }))
  await user.click(screen.getByRole('button', { name: '볶음밥 더하기' }))
}

describe('테이블 태블릿 흐름', () => {
  it('T1: 담기 전에는 주문 확인이 꺼져 있고, 담으면 개수와 합계가 바뀐다', async () => {
    const { api } = controlledApi()
    render(<TableApp tableId="T3" api={api} />)
    const user = userEvent.setup()

    expect(screen.getByText('T3 테이블')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '주문 확인' })).toBeDisabled()
    expect(await screen.findByRole('button', { name: '치킨 빼기' })).toBeDisabled()

    await orderChickenAndRice(user)
    expect(screen.getByText('담은 메뉴 3개')).toBeInTheDocument()
    expect(screen.getByText(won(18000 + 9000 * 2))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '볶음밥 빼기' }))
    expect(screen.getByText('담은 메뉴 2개')).toBeInTheDocument()
  })

  it('T1 → T2 → 수정 → T2 → 주문하기 → T3', async () => {
    const { api } = controlledApi()
    render(<TableApp tableId="T3" api={api} />)
    const user = userEvent.setup()

    await orderChickenAndRice(user)
    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    expect(screen.getByRole('heading', { name: '이대로 주문할까요?' })).toBeInTheDocument()
    expect(screen.getByText(won(36000))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '수정' }))
    expect(screen.getByText('담은 메뉴 3개')).toBeInTheDocument() // 담은 것 유지

    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    await user.click(screen.getByRole('button', { name: '주문하기' }))

    expect(api.placeOrder).toHaveBeenCalledWith('T3', [
      { menuId: 'chicken', qty: 1 },
      { menuId: 'friedrice', qty: 2 },
    ])
    expect(await screen.findByText('주문 ORD-0012')).toBeInTheDocument()
    expect(screen.getByText('도착 예정')).toBeInTheDocument()
    expect(screen.getByText('약 6분 뒤')).toBeInTheDocument()
  })

  it('T3: 단계 표시와 메뉴별 상태 (시안: 치킨 서빙 준비 완료, 볶음밥 조리 중)', async () => {
    const { api } = controlledApi([order()])
    render(<TableApp tableId="T3" api={api} />)

    expect(await screen.findByText('주문 ORD-0012')).toBeInTheDocument()
    const track = screen.getByRole('list', { name: '주문 진행 단계' })
    expect(within(track).getByText('조리 중').closest('[aria-current]')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('서빙 준비 완료')).toBeInTheDocument()
    expect(screen.getByText('로봇팔이 조리 중')).toBeInTheDocument()
  })

  it('서빙 로봇이 오면 T4로 바뀌고, 전달이 끝나면 T3로 돌아온다', async () => {
    const o = order({ stage: 'serving' })
    const { api, push } = controlledApi([o])
    render(<TableApp tableId="T3" api={api} />)
    push({
      tableId: 'T3',
      session: 'active',
      orders: [o],
      delivery: { orderId: o.orderId, itemNames: ['치킨'], step: 'transferring' },
    })

    expect(await screen.findByRole('heading', { name: /치킨\s*이\s*도착했어요/ })).toBeInTheDocument()
    expect(screen.getByText('음식 도착')).toBeInTheDocument()
    expect(screen.getByText('테이블로 옮기는 중').closest('li')).toHaveAttribute('aria-current', 'step')

    push({ tableId: 'T3', session: 'active', orders: [o], delivery: null })
    expect(screen.getByText('주문 ORD-0012')).toBeInTheDocument()
  })

  it('T3 → 이용 종료 → T5 확인창: 계속 이용은 닫기, 이용 종료는 종료 화면', async () => {
    const { api, push } = controlledApi([order()])
    render(<TableApp tableId="T3" api={api} />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '이용 종료' }))
    expect(screen.getByRole('dialog', { name: '이용을 마칠까요?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '계속 이용' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '이용 종료' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '이용 종료' }))
    expect(api.endSession).toHaveBeenCalledWith('T3')
    expect(await screen.findByText('이용해 주셔서 고마워요')).toBeInTheDocument()

    // 정리 후 다음 손님 → 메뉴 화면
    push({ tableId: 'T3', session: 'active', orders: [], delivery: null })
    expect(screen.getByRole('heading', { name: '무엇을 드실래요?' })).toBeInTheDocument()
  })

  it('가짜 API로 주문부터 전달 완료까지 끝까지 흘러간다', async () => {
    render(<TableApp tableId="T3" api={createMockTableApi({ tickMs: 30 })} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '치킨 더하기' }))
    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    await user.click(screen.getByRole('button', { name: '주문하기' }))

    expect(await screen.findByText('주문 ORD-0012')).toBeInTheDocument()
    expect(await screen.findByText('음식 도착')).toBeInTheDocument()
    // T4가 끝나면 T3로 돌아와 '전달 완료'
    expect(await screen.findByText('주문 상태', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getAllByText('전달 완료').length).toBeGreaterThan(0)
  })
})

describe('표시 형식', () => {
  it('받침에 따라 이/가', () => {
    expect(subjectJosa('치킨')).toBe('이')
    expect(subjectJosa('볶음밥')).toBe('이')
    expect(subjectJosa('피자')).toBe('가')
  })
  it('남은 시간', () => {
    const now = new Date('2026-11-20T16:42:00')
    expect(minutesFromNow('2026-11-20T16:48:00', now)).toBe('약 6분 뒤')
    expect(minutesFromNow('2026-11-20T16:42:20', now)).toBe('곧 도착')
  })
  it('가격', () => {
    expect(won(36000)).toBe('36,000원')
  })
})
