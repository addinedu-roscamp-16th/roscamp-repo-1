import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getDataMode, isMockPath } from './api'
import { Home } from './Home'

describe('화면 목록', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('/mock 으로 시작하는 주소만 목업', () => {
    expect(isMockPath('/mock')).toBe(true)
    expect(isMockPath('/mock/admin/tables')).toBe(true)
    expect(isMockPath('/admin')).toBe(false)
    expect(isMockPath('/mockup')).toBe(false)
    expect(getDataMode()).toBe('server')
  })

  it('화면마다 버튼 하나, 위에서 고른 쪽 주소로 열린다', () => {
    const { unmount } = render(<Home mode="server" />)
    expect(screen.getByRole('link', { name: /입구 키오스크/ })).toHaveAttribute('href', '/kiosk')
    expect(screen.getByRole('link', { name: '서버' })).toHaveAttribute('aria-current', 'page')
    unmount()

    render(<Home mode="mock" />)
    expect(screen.getByRole('link', { name: /^입구 키오스크 K1~K4/ })).toHaveAttribute('href', '/mock/kiosk')
    expect(screen.getByRole('link', { name: /로봇 대기 흐름/ })).toHaveAttribute('href', '/mock/kiosk?robot=busy')
    expect(screen.getByRole('link', { name: '목업 데이터' })).toHaveAttribute('aria-current', 'page')
  })

  it('배포 파일: 목업 선택과 점검 링크가 없다', () => {
    vi.stubEnv('DEV', false)
    render(<Home mode="server" />)
    expect(screen.queryByRole('link', { name: '목업 데이터' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /백엔드 연결 점검/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /관리자 PC · 통합 관제/ })).toHaveAttribute('href', '/admin')
  })
})
