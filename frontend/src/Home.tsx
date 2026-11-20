import { getDataMode, MOCK_BASE, type DataMode } from './api'

/**
 * 화면 목록. 화면마다 버튼 하나.
 * 위쪽에서 "진짜 서버 / 목업 데이터"를 고르면 목록 전체가 그쪽 주소로 바뀝니다
 * (진짜 서버 = 기본 주소 /, 목업 = /mock). 목업은 개발 서버에서만.
 */
export function Home({ mode = getDataMode() }: { mode?: DataMode }) {
  // 배포 빌드에서는 목업 관련 부분이 통째로 빠짐
  const mockEnabled = import.meta.env.DEV
  const mock = mockEnabled && mode === 'mock'
  const base = mock ? MOCK_BASE : ''
  const screens = [
    { path: '/kiosk', label: '입구 키오스크', note: 'K1~K4' },
    ...(mock ? [{ path: '/kiosk?robot=busy', label: '입구 키오스크 · 로봇 대기 흐름', note: 'K1→K2→K3→K4' }] : []),
    { path: '/table/3', label: '테이블 태블릿 (3번 테이블)', note: 'T1~T5' },
    { path: '/admin', label: '관리자 PC · 통합 관제', note: 'A1' },
    { path: '/admin/tables', label: '관리자 PC · 테이블·주문', note: 'A2' },
    { path: '/admin/alarms', label: '관리자 PC · 알람·이력', note: 'A3' },
  ]
  const seg = (on: boolean, accent: boolean) => ({
    display: 'inline-flex',
    alignItems: 'center',
    height: 40,
    padding: '0 16px',
    borderRadius: 9,
    fontWeight: 700,
    fontSize: 14,
    textDecoration: 'none',
    background: on ? (accent ? 'var(--c-accent)' : 'var(--c-text)') : 'transparent',
    color: on ? '#fff' : 'var(--c-text-sub)',
  })

  return (
    <main style={{ maxWidth: 560, margin: '0 auto', padding: '48px 16px' }}>
      <h1 style={{ fontSize: 28, fontWeight: 800, margin: '0 0 16px' }}>OneTeam 레스토랑 화면</h1>

      {mockEnabled && (
        <nav aria-label="데이터" style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div style={{ display: 'inline-flex', gap: 4, padding: 4, borderRadius: 12, background: '#fff' }}>
            <a href="/" aria-current={!mock ? 'page' : undefined} style={seg(!mock, false)}>
              진짜 서버
            </a>
            <a href={MOCK_BASE} aria-current={mock ? 'page' : undefined} style={seg(mock, true)}>
              목업 데이터
            </a>
          </div>
          <span style={{ color: 'var(--c-text-sub)', fontSize: 14 }}>
            {mock ? '서버 없이 화면만 움직여 봐요' : '백엔드 서버와 주고받아요'}
          </span>
        </nav>
      )}

      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 12 }}>
        {screens.map((sc) => (
          <li key={sc.path}>
            <a
              href={base + sc.path}
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
              <span>{sc.label}</span>
              <span style={{ color: 'var(--c-text-sub)', fontWeight: 500 }}>{sc.note}</span>
            </a>
          </li>
        ))}
      </ul>

      {mockEnabled && (
        <a href="/check" style={{ display: 'inline-block', marginTop: 24, color: 'var(--c-text-sub)', fontSize: 14 }}>
          백엔드 연결 점검 (백엔드 개발자용) →
        </a>
      )}
    </main>
  )
}
