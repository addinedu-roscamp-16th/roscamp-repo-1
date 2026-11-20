import { BrowserRouter, Link, Route, Routes, useParams } from 'react-router-dom'
import { KioskApp } from './kiosk/KioskApp'
import { TableApp } from './table/TableApp'

/**
 * 기기별 화면을 주소로 나눕니다.
 *   /kiosk         입구 키오스크 (K1~K4)
 *   /table/:id     테이블 태블릿 (T1~T5)
 *   /admin         관리자 PC (A1~A3) — 준비 중
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/kiosk" element={<KioskApp />} />
        <Route path="/table/:tableId" element={<TableRoute />} />
        <Route path="/admin" element={<Placeholder title="관리자 PC (A1~A3)" />} />
        <Route path="*" element={<Placeholder title="없는 주소예요" />} />
      </Routes>
    </BrowserRouter>
  )
}

function Home() {
  const links = [
    { to: '/kiosk', label: '입구 키오스크', note: 'K1~K4' },
    { to: '/kiosk?robot=busy', label: '입구 키오스크 · 로봇 대기 흐름', note: 'K1→K2→K3→K4' },
    { to: '/table/T3', label: '테이블 태블릿 (T3 테이블)', note: 'T1~T5' },
    { to: '/admin', label: '관리자 PC', note: 'A1~A3 · 준비 중' },
  ]
  return (
    <main style={{ maxWidth: 560, margin: '0 auto', padding: '48px 16px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 24px' }}>OneTeam 레스토랑 화면</h1>
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
    </main>
  )
}

function TableRoute() {
  const { tableId = '' } = useParams()
  // 주소가 바뀌면 다른 테이블이므로 상태를 새로 시작
  return <TableApp key={tableId} tableId={tableId.toUpperCase()} />
}

function Placeholder({ title }: { title: string }) {
  return (
    <main style={{ maxWidth: 560, margin: '0 auto', padding: '48px 16px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 800 }}>{title}</h1>
      <p style={{ color: 'var(--c-text-sub)' }}>아직 구현하지 않은 화면이에요.</p>
      <Link to="/">← 화면 목록</Link>
    </main>
  )
}
