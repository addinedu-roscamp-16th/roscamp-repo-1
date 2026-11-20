import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { getDataMode, isMockPath } from './api'
import { Home } from './Home'

describe('목업 / 진짜 서버 주소', () => {
  it('/mock 으로 시작하는 주소만 목업', () => {
    expect(isMockPath('/mock')).toBe(true)
    expect(isMockPath('/mock/admin/tables')).toBe(true)
    expect(isMockPath('/admin')).toBe(false)
    expect(isMockPath('/mockup')).toBe(false)
    expect(getDataMode()).toBe('server') // 테스트 주소는 '/'
  })

  it('진짜 서버 목록: 목업 전용 메뉴는 없고 목업 목록으로 가는 링크가 있다', () => {
    render(
      <MemoryRouter>
        <Home mode="server" />
      </MemoryRouter>,
    )
    expect(screen.getByText(/진짜 서버 — 백엔드/)).toBeInTheDocument()
    expect(screen.queryByText(/로봇 대기 흐름/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '목업 데이터 화면 목록 →' })).toHaveAttribute('href', '/mock')
  })

  it('목업 목록: 로봇 대기 흐름 메뉴가 있다', () => {
    render(
      <MemoryRouter>
        <Home mode="mock" />
      </MemoryRouter>,
    )
    expect(screen.getByText(/목업 데이터 — 서버 없이/)).toBeInTheDocument()
    expect(screen.getByText('입구 키오스크 · 로봇 대기 흐름')).toBeInTheDocument()
  })
})
