import { Link } from 'react-router-dom'
import { getDataMode, MOCK_BASE, type DataMode } from './api'

/** 화면 목록. 기본 주소는 진짜 서버, /mock 주소는 목업 데이터 */
export function Home({ mode = getDataMode() }: { mode?: DataMode }) {
  const mock = mode === 'mock'
  const links = [
    { to: '/kiosk', label: '입구 키오스크', note: 'K1~K4' },
    ...(mock ? [{ to: '/kiosk?robot=busy', label: '입구 키오스크 · 로봇 대기 흐름', note: 'K1→K2→K3→K4' }] : []),
    { to: '/table/3', label: '테이블 태블릿 (3번 테이블)', note: 'T1~T5' },
    { to: '/admin', label: '관리자 PC · 통합 관제', note: 'A1' },
    { to: '/admin/tables', label: '관리자 PC · 테이블·주문', note: 'A2' },
    { to: '/admin/alarms', label: '관리자 PC · 알람·이력', note: 'A3' },
  ]
  return (
    <main style={{ maxWidth: 560, margin: '0 auto', padding: '48px 16px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px' }}>OneTeam 레스토랑 화면</h1>
      <p style={{ margin: '0 0 24px', color: mock ? 'var(--c-accent-text)' : 'var(--c-text-sub)', fontWeight: 700 }}>
        {mock ? '목업 데이터 — 서버 없이 화면만 움직여 봐요' : '진짜 서버 — 백엔드(frontend/.env 의 BACKEND_URL)와 주고받아요'}
      </p>

      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 12 }}>
        {links.map((l) => (
          <li key={l.to}>
            <Link
              to={l.to}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                padding: '18px 20px',
                borderRadius: 16,
                background: '#fff',
                color: 'var(--c-text)',
                textDecoration: 'none',
                fontWeight: 700,
              }}
            >
              <span>{l.label}</span>
              <span style={{ color: 'var(--c-text-sub)', fontWeight: 500 }}>{l.note}</span>
            </Link>
          </li>
        ))}
      </ul>

      <p style={{ marginTop: 24, color: 'var(--c-text-sub)', fontSize: 14, lineHeight: 1.6 }}>
        {mock ? (
          <>
            진짜 서버로 보려면 주소에서 <code>{MOCK_BASE}</code>를 빼세요. <a href="/">진짜 서버 화면 목록 →</a>
          </>
        ) : (
          <>
            서버 없이 보려면 주소 앞에 <code>{MOCK_BASE}</code>를 붙이세요 (예: <code>{MOCK_BASE}/kiosk</code>).{' '}
            <a href={MOCK_BASE}>목업 데이터 화면 목록 →</a>
          </>
        )}
      </p>
    </main>
  )
}
