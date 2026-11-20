import { Link } from 'react-router-dom'
import { getDataMode, setDataMode, type DataMode } from './api'

/** 화면 목록 + 가짜 데이터 / 진짜 서버 스위치 */
export function Home({ mode = getDataMode(), onChange = setDataMode }: { mode?: DataMode; onChange?: (m: DataMode) => void }) {
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
      <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 24px' }}>OneTeam 레스토랑 화면</h1>

      <section
        aria-label="데이터 연결"
        style={{
          marginBottom: 24,
          padding: '18px 20px',
          borderRadius: 16,
          background: mock ? 'var(--c-accent-soft)' : 'var(--c-ok-bg)',
          border: `2px solid ${mock ? 'var(--c-accent)' : 'var(--c-ok-icon)'}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <b style={{ fontSize: 18, flexGrow: 1, color: mock ? 'var(--c-accent-text)' : 'var(--c-ok-text)' }}>
            {mock ? '지금 가짜 데이터예요' : '지금 진짜 서버에 붙어 있어요'}
          </b>
          <div role="radiogroup" aria-label="데이터" style={{ display: 'flex', gap: 4, padding: 4, borderRadius: 12, background: '#fff' }}>
            {(['mock', 'server'] as DataMode[]).map((m) => (
              <button
                key={m}
                role="radio"
                aria-checked={mode === m}
                onClick={() => mode !== m && onChange(m)}
                style={{
                  height: 40,
                  padding: '0 14px',
                  border: 0,
                  borderRadius: 9,
                  fontWeight: 700,
                  background: mode === m ? (m === 'mock' ? 'var(--c-accent)' : 'var(--c-ok-icon)') : 'transparent',
                  color: mode === m ? '#fff' : 'var(--c-text-sub)',
                }}
              >
                {m === 'mock' ? '가짜 데이터' : '진짜 서버'}
              </button>
            ))}
          </div>
        </div>
        <p style={{ margin: '8px 0 0', color: 'var(--c-text-sub)', fontSize: 14, lineHeight: 1.6 }}>
          {mock
            ? '서버 없이 화면만 움직여 봐요. 로봇·주문은 흉내 낸 것이에요.'
            : '백엔드 서버(frontend/.env 의 BACKEND_URL)와 주고받아요. 서버가 꺼져 있으면 화면이 비어 보여요.'}
          <br />이 기기에서만 바뀌고, 다음에 열어도 그대로예요.
        </p>
      </section>

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
