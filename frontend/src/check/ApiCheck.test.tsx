import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiCheck } from './ApiCheck'

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }))

describe('백엔드 연결 점검', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('있는 것은 됨, 없는 것은 아직 없음, 칸이 빠지면 모양 다름', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url === '/api/health') return json(200, { ok: true })
        if (url === '/api/menu') return json(200, [{ menu_id: 1, name: '치킨', is_available: true }]) // price 빠짐
        if (url === '/api/tables') return json(200, [])
        return json(404, {})
      }),
    )
    vi.stubGlobal(
      'WebSocket',
      class {
        onerror: (() => void) | null = null
        constructor() {
          setTimeout(() => this.onerror?.(), 0)
        }
        close() {}
      },
    )
    render(<ApiCheck />)
    const step = (name: string) => screen.getByRole('listitem', { name })
    expect(await within(step('1단계 서버 켜짐')).findByText('됨')).toBeInTheDocument()
    expect(await within(step('2단계 메뉴')).findByText('빠진 칸: price')).toBeInTheDocument()
    expect(await within(step('3단계 테이블 목록')).findByText('됨 · 테이블 0개')).toBeInTheDocument()
    expect(await within(step('9단계 관리자 현황')).findByText('아직 없음')).toBeInTheDocument()
    // 접수는 로봇이 움직일 수 있어 자동으로 보내지 않음
    expect(within(step('4단계 입구 접수')).getByText('화면에서 확인')).toBeInTheDocument()
    expect(within(step('4단계 입구 접수')).getByRole('link', { name: '목업에서 보기' })).toHaveAttribute('href', '/mock/kiosk')
  })

  it('서버가 꺼져 있으면 서버 꺼짐', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('fail'))))
    render(<ApiCheck />)
    expect(await within(screen.getByRole('listitem', { name: '1단계 서버 켜짐' })).findByText('서버 꺼짐')).toBeInTheDocument()
  })
})
