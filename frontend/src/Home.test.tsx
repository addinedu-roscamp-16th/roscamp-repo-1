import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { getDataMode, isMockPath } from './api'
import { Home } from './Home'

describe('화면 목록', () => {
  it('/mock 으로 시작하는 주소만 목업', () => {
    expect(isMockPath('/mock')).toBe(true)
    expect(isMockPath('/mock/admin/tables')).toBe(true)
    expect(isMockPath('/admin')).toBe(false)
    expect(isMockPath('/mockup')).toBe(false)
    expect(getDataMode()).toBe('server')
  })

  it('화면마다 진짜 서버 / 목업 데이터를 골라 연다', () => {
    render(<Home mode="server" />)
    const row = screen.getByRole('listitem', { name: '입구 키오스크' })
    expect(within(row).getByRole('link', { name: '진짜 서버' })).toHaveAttribute('href', '/kiosk')
    expect(within(row).getByRole('link', { name: '목업 데이터' })).toHaveAttribute('href', '/mock/kiosk')
    expect(screen.getByRole('link', { name: /백엔드 연결 점검/ })).toHaveAttribute('href', '/check')
  })
})
