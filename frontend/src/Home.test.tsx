import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { getDataMode } from './api'
import { Home } from './Home'

describe('첫 화면 데이터 스위치', () => {
  it('기본은 가짜 데이터이고, 진짜 서버를 누르면 바뀐다', async () => {
    expect(getDataMode()).toBe('mock')
    const onChange = vi.fn()
    render(
      <MemoryRouter>
        <Home mode="mock" onChange={onChange} />
      </MemoryRouter>,
    )
    expect(screen.getByText('지금 가짜 데이터예요')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: '가짜 데이터' })).toBeChecked()
    await userEvent.setup().click(screen.getByRole('radio', { name: '진짜 서버' }))
    expect(onChange).toHaveBeenCalledWith('server')
  })

  it('진짜 서버일 때는 가짜 전용 메뉴(로봇 대기 흐름)를 숨긴다', () => {
    render(
      <MemoryRouter>
        <Home mode="server" onChange={() => {}} />
      </MemoryRouter>,
    )
    expect(screen.getByText('지금 진짜 서버에 붙어 있어요')).toBeInTheDocument()
    expect(screen.queryByText(/로봇 대기 흐름/)).not.toBeInTheDocument()
  })
})
