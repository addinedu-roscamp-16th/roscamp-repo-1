import { BrowserRouter, Link, Route, Routes, useParams } from 'react-router-dom'
import { AdminApp } from './admin/AdminApp'
import { ApiCheck } from './check/ApiCheck'
import { KioskApp } from './kiosk/KioskApp'
import { getDataMode, MOCK_BASE } from './api'
import { tableSpec } from './api/storeLayout'
import { Home } from './Home'
import { TableApp } from './table/TableApp'

/**
 * 기기별 화면을 주소로 나눕니다.
 *   /kiosk         입구 키오스크 (K1~K4)
 *   /table/:id     테이블 태블릿 (T1~T5)
 *   /admin         관리자 PC — A1 통합 관제, /admin/tables A2, /admin/alarms A3
 * 같은 주소 앞에 /mock 을 붙이면 목업 데이터로 봅니다 (예: /mock/kiosk). 화면 구성은 똑같습니다.
 */
export default function App() {
  const mock = getDataMode() === 'mock'
  return (
    <BrowserRouter basename={mock ? MOCK_BASE : undefined}>
      {mock && <MockBadge />}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/kiosk" element={<KioskApp />} />
        <Route path="/table/:tableId" element={<TableRoute />} />
        <Route path="/admin/*" element={<AdminApp />} />
        <Route path="/check" element={<ApiCheck />} />
        <Route path="*" element={<Placeholder title="없는 주소예요" />} />
      </Routes>
    </BrowserRouter>
  )
}

function TableRoute() {
  const { tableId = '' } = useParams()
  // "/table/5" 또는 "/table/T5" 모두 5번 테이블
  const id = Number(tableId.replace(/^t/i, ''))
  if (!tableSpec(id)) return <Placeholder title={`없는 테이블이에요 (${tableId})`} />
  // 주소가 바뀌면 다른 테이블이므로 상태를 새로 시작
  return <TableApp key={id} tableId={id} />
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

/** 목업 데이터로 보는 중임을 모든 화면 구석에 표시 (진짜 서버와 헷갈리지 않게) */
function MockBadge() {
  return (
    <div
      role="note"
      aria-label="목업 데이터 화면"
      style={{
        position: 'fixed',
        left: 8,
        bottom: 8,
        zIndex: 1000,
        padding: '4px 10px',
        borderRadius: 999,
        background: '#F0640F',
        color: '#fff',
        fontSize: 12,
        fontWeight: 700,
        opacity: 0.9,
        pointerEvents: 'none',
      }}
    >
      목업 데이터
    </div>
  )
}
