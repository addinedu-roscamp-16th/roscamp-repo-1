import { getDataMode, MOCK_BASE, type DataMode } from './api'

/**
 * 화면 목록. 화면마다 [진짜 서버] [목업 데이터] 중 골라서 엽니다.
 * 진짜 서버 = 기본 주소, 목업 데이터 = 같은 주소 앞에 /mock.
 */
export function Home({ mode = getDataMode() }: { mode?: DataMode }) {
  // 목업은 개발 서버에서만 (배포 빌드에서는 이 부분이 통째로 빠짐)
  const mockEnabled = import.meta.env.DEV
  const screens = [
    { path: '/kiosk', label: '입구 키오스크', note: 'K1~K4' },
    { path: '/table/3', label: '테이블 태블릿 (3번 테이블)', note: 'T1~T5' },
    { path: '/admin', label: '관리자 PC · 통합 관제', note: 'A1' },
    { path: '/admin/tables', label: '관리자 PC · 테이블·주문', note: 'A2' },
    { path: '/admin/alarms', label: '관리자 PC · 알람·이력', note: 'A3' },
  ]
  const btn = (primary: boolean) => ({
    display: 'inline-flex',
    alignItems: 'center',
    height: 40,
    padding: '0 14px',
    borderRadius: 10,
    fontWeight: 700,
    fontSize: 14,
    textDecoration: 'none',
    whiteSpace: 'nowrap' as const,
    background: primary ? 'var(--c-text)' : 'var(--c-accent-soft)',
    color: primary ? '#fff' : 'var(--c-accent-text)',
  })
  return (
    <main style={{ maxWidth: 640, margin: '0 auto', padding: '48px 16px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 8px' }}>OneTeam 레스토랑 화면</h1>
      <p style={{ margin: '0 0 24px', color: 'var(--c-text-sub)', lineHeight: 1.6 }}>
        <b>진짜 서버</b>: 백엔드(<code>frontend/.env</code>의 BACKEND_URL)와 주고받아요.
        {mockEnabled && (
          <>
            <br />
            <b style={{ color: 'var(--c-accent-text)' }}>목업 데이터</b>: 서버 없이 화면만 움직여 봐요 (주소 앞에{' '}
            <code>{MOCK_BASE}</code>, 개발 서버에서만).
            {mode === 'mock' && <> 지금 목업 주소로 열려 있어요.</>}
          </>
        )}
      </p>

      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 12 }}>
        {screens.map((sc) => (
          <li
            key={sc.path}
            aria-label={sc.label}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '14px 16px 14px 20px',
              borderRadius: 16,
              background: '#fff',
            }}
          >
            <span style={{ fontWeight: 700, flexGrow: 1 }}>
              {sc.label} <span style={{ color: 'var(--c-text-sub)', fontWeight: 500 }}>{sc.note}</span>
            </span>
            <a href={sc.path} style={btn(true)}>
              진짜 서버
            </a>
            {mockEnabled && (
              <a href={MOCK_BASE + sc.path} style={btn(false)}>
                목업 데이터
              </a>
            )}
          </li>
        ))}
        {mockEnabled && (
          <li
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '14px 16px 14px 20px',
              borderRadius: 16,
              background: '#fff',
            }}
          >
            <span style={{ fontWeight: 700, flexGrow: 1 }}>
              입구 키오스크 · 로봇 대기 흐름{' '}
              <span style={{ color: 'var(--c-text-sub)', fontWeight: 500 }}>K1→K2→K3→K4</span>
            </span>
            <a href={`${MOCK_BASE}/kiosk?robot=busy`} style={btn(false)}>
              목업 데이터
            </a>
          </li>
        )}
      </ul>

      {mockEnabled && (
        <a
          href="/check"
          style={{
            display: 'block',
            marginTop: 24,
            padding: '18px 20px',
            borderRadius: 16,
            border: '2px dashed var(--c-line)',
            color: 'var(--c-text)',
            textDecoration: 'none',
          }}
        >
          <b>백엔드 연결 점검 →</b>
          <br />
          <span style={{ color: 'var(--c-text-sub)', fontSize: 14 }}>
            무엇을 어떤 순서로 붙이면 되는지, 지금 무엇이 됐는지 보여 줘요 (백엔드 개발자용)
          </span>
        </a>
      )}
    </main>
  )
}
