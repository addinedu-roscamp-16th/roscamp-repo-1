import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { createMockApi } from '../api/mockApi'
import { fakeApi, orderOf, tableOf, visitOf } from '../test/fakeApi'
import { minutesFromNow, subjectJosa, won } from './format'
import { TableApp } from './TableApp'

async function addChickenAndTwoRice(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: '치킨 더하기' }))
  await user.click(screen.getByRole('button', { name: '볶음밥 더하기' }))
  await user.click(screen.getByRole('button', { name: '볶음밥 더하기' }))
}

function seated(orders = [] as ReturnType<typeof orderOf>[], over = {}) {
  const f = fakeApi()
  f.seed(tableOf(), visitOf({ orders, ...over }))
  return f
}

describe('테이블 태블릿 흐름', () => {
  it('T1: 담기 전에는 주문 확인이 꺼져 있고, 담으면 개수와 합계가 바뀐다', async () => {
    const { api } = seated()
    render(<TableApp tableId={3} api={api} />)
    const user = userEvent.setup()

    expect(screen.getByText('3번 테이블')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '주문 확인' })).toBeDisabled()
    expect(await screen.findByRole('button', { name: '치킨 빼기' })).toBeDisabled()

    await addChickenAndTwoRice(user)
    expect(screen.getByText('담은 메뉴 3개')).toBeInTheDocument()
    expect(screen.getByText(won(18000 + 9000 * 2))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '볶음밥 빼기' }))
    expect(screen.getByText('담은 메뉴 2개')).toBeInTheDocument()
  })

  it('T1 → T2 → 수정 → T2 → 주문하기: WEB-04 형식으로 보낸다', async () => {
    const f = seated()
    render(<TableApp tableId={3} api={f.api} />)
    const user = userEvent.setup()

    await addChickenAndTwoRice(user)
    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    expect(screen.getByRole('heading', { name: '이대로 주문할까요?' })).toBeInTheDocument()
    expect(screen.getByText(won(36000))).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '수정' }))
    expect(screen.getByText('담은 메뉴 3개')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    await user.click(screen.getByRole('button', { name: '주문하기' }))

    expect(f.api.createOrder).toHaveBeenCalledWith({
      visit_id: 'v1',
      table_id: 3,
      items: [
        { menu_id: 1, qty: 1 },
        { menu_id: 2, qty: 2 },
      ],
      request_key: expect.any(String),
    })
  })

  it('주문 결과가 불명이면 같은 요청 키로 다시 보낸다', async () => {
    const createOrder = vi
      .fn()
      .mockRejectedValueOnce(new ApiError('RESULT_UNCONFIRMED', 503))
      .mockResolvedValueOnce({ order_id: 'ORD-0012', status: 'ORDERED' })
    const f = fakeApi({ createOrder })
    f.seed(tableOf(), visitOf())
    render(<TableApp tableId={3} api={f.api} />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '치킨 더하기' }))
    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    await user.click(screen.getByRole('button', { name: '주문하기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('한 번 더 눌러 주세요')
    await user.click(screen.getByRole('button', { name: '주문하기' }))

    const [a, b] = createOrder.mock.calls.map((c) => c[0])
    expect(b.request_key).toBe(a.request_key)
  })

  it('T3: 단계 표시와 메뉴별 상태 (시안: 치킨 서빙 준비 완료, 볶음밥 조리 중)', async () => {
    const { api } = seated([orderOf()])
    render(<TableApp tableId={3} api={api} />)

    expect(await screen.findByText('주문 ORD-0012')).toBeInTheDocument()
    const track = screen.getByRole('list', { name: '주문 진행 단계' })
    expect(within(track).getByText('조리 중').closest('[aria-current]')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('서빙 준비 완료')).toBeInTheDocument()
    expect(screen.getByText('로봇팔이 조리 중')).toBeInTheDocument()
    expect(screen.getByText('약 6분 뒤')).toBeInTheDocument()
  })

  it('주문이 ARRIVED면 T4, COMPLETED가 되면 T3로 돌아온다', async () => {
    const f = seated([orderOf({ status: 'ARRIVED', delivery_step: 'TRANSFERRING' })])
    render(<TableApp tableId={3} api={f.api} />)

    expect(await screen.findByRole('heading', { name: /치킨, 볶음밥\s*이\s*도착했어요/ })).toBeInTheDocument()
    expect(screen.getByText('음식 도착')).toBeInTheDocument()
    expect(screen.getByText('테이블로 옮기는 중').closest('li')).toHaveAttribute('aria-current', 'step')

    f.setVisit(visitOf({ orders: [orderOf({ status: 'COMPLETED', eta_at: null })] }))
    expect(screen.getByText('주문 ORD-0012')).toBeInTheDocument()
    expect(screen.getByText('주문 상태')).toBeInTheDocument()
  })

  it('T3 → 이용 종료 → T5: 계속 이용은 닫기, 이용 종료는 WEB-06 후 종료 화면', async () => {
    const f = seated([orderOf({ status: 'COMPLETED' })])
    render(<TableApp tableId={3} api={f.api} />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '이용 종료' }))
    expect(screen.getByRole('dialog', { name: '이용을 마칠까요?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '계속 이용' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '이용 종료' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: '이용 종료' }))
    expect(f.api.endVisit).toHaveBeenCalledWith('v1', expect.any(String))

    f.setTable(tableOf({ status: 'CLEANING' }))
    expect(screen.getByText('이용해 주셔서 고마워요')).toBeInTheDocument()

    // 정리 후 다음 손님 → 메뉴 화면
    f.setVisit(visitOf({ visit_id: 'v2' }))
    f.setTable(tableOf({ status: 'IN_USE', visit_id: 'v2' }))
    expect(await screen.findByRole('heading', { name: '무엇을 드실래요?' })).toBeInTheDocument()
  })

  it('받지 않은 음식이 있으면(can_end=false) 종료 창 대신 안내', async () => {
    const { api } = seated([orderOf()], { can_end: false })
    render(<TableApp tableId={3} api={api} />)
    await userEvent.setup().click(await screen.findByRole('button', { name: '이용 종료' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('아직 받지 않은 음식이 있어요')
  })

  it('가격 정보가 없으면 합계를 보류한다 (WEB-03)', async () => {
    const f = fakeApi({
      getMenu: async () => [{ menu_id: 1, name: '치킨', price: null, is_available: true }],
    })
    f.seed(tableOf(), visitOf())
    render(<TableApp tableId={3} api={f.api} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '치킨 더하기' }))
    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    expect(screen.getByText('가격 확인 중')).toBeInTheDocument()
  })

  it('가짜 API로 주문부터 전달 완료까지 끝까지 흘러간다', async () => {
    render(<TableApp tableId={3} api={createMockApi({ tickMs: 30, autoSeat: true })} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '치킨 더하기' }))
    await user.click(screen.getByRole('button', { name: '주문 확인' }))
    await user.click(screen.getByRole('button', { name: '주문하기' }))

    expect(await screen.findByText('주문 ORD-0012')).toBeInTheDocument()
    expect(await screen.findByText('음식 도착')).toBeInTheDocument()
    expect(await screen.findByText('주문 상태', {}, { timeout: 3000 })).toBeInTheDocument()
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

describe('서버 연결이 안 될 때', () => {
  it('메뉴를 못 불러오면 안내와 다시 불러오기 버튼이 나오고, 누르면 다시 부른다', async () => {
    const getMenu = vi.fn().mockRejectedValueOnce(new ApiError('NETWORK')).mockResolvedValueOnce([
      { menu_id: 1, name: '치킨', price: 18000, is_available: true },
    ])
    const f = fakeApi({ getMenu })
    f.seed(tableOf(), visitOf())
    render(<TableApp tableId={3} api={f.api} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('메뉴를 불러오지 못했어요')
    await userEvent.setup().click(screen.getByRole('button', { name: '다시 불러오기' }))
    expect(await screen.findByRole('button', { name: '치킨 더하기' })).toBeInTheDocument()
  })
})
