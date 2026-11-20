import { useCallback, useEffect, useState } from 'react'
import { MOCK_BASE } from '../api'

/**
 * 백엔드 개발자용 연결 점검 (/check).
 * Confluence I/F 목록을 붙이는 순서대로 늘어놓고, 읽기만 하는 요청(GET·WebSocket)은 눌러서 바로 확인합니다.
 * 접수·주문처럼 매장 상태를 바꾸는 요청은 로봇이 움직일 수 있어 자동으로 보내지 않고, 확인할 화면을 알려 줍니다.
 */

type Result =
  | { kind: 'idle' }
  | { kind: 'running' }
  | { kind: 'ok'; text: string }
  | { kind: 'shape'; text: string }
  | { kind: 'missing'; text: string }
  | { kind: 'down'; text: string }

interface Step {
  no: number
  title: string
  iface: string
  /** 이 요청을 쓰는 화면 (진짜 서버 주소) */
  screen: { label: string; path: string } | null
  /** 자동 확인. 없으면 화면에서 직접 확인 */
  auto?: (ctx: { visitId: string | null }) => Promise<Result>
  /** 직접 확인하는 방법 */
  how: string
}

const API = '/api'

async function getJson(path: string): Promise<{ status: number; body: unknown } | null> {
  try {
    const res = await fetch(API + path)
    let body: unknown = null
    try {
      body = await res.json()
    } catch {
      /* 본문 없음 */
    }
    return { status: res.status, body }
  } catch {
    return null
  }
}

/** 응답에 화면이 쓰는 칸이 다 있는지 */
function missingKeys(obj: unknown, keys: string[]) {
  if (!obj || typeof obj !== 'object') return keys
  return keys.filter((k) => !(k in (obj as Record<string, unknown>)))
}

function judge(r: Awaited<ReturnType<typeof getJson>>, check: (body: unknown) => Result): Result {
  if (!r) return { kind: 'down', text: '서버에 닿지 않아요 (서버가 꺼졌거나 BACKEND_URL이 달라요)' }
  if (r.status === 404 || r.status === 405 || r.status === 501) return { kind: 'missing', text: `아직 없어요 (HTTP ${r.status})` }
  if (r.status >= 500 && r.status !== 503)
    return { kind: 'down', text: `HTTP ${r.status} — 서버가 꺼져 있거나(BACKEND_URL 확인) 서버 코드에서 오류가 났어요` }
  if (r.status >= 400) return { kind: 'shape', text: `HTTP ${r.status} — 요청은 닿았지만 거절됐어요` }
  return check(r.body)
}

const listOf = (keys: string[], what: string) => (body: unknown): Result => {
  if (!Array.isArray(body)) return { kind: 'shape', text: `목록([...])이 와야 해요` }
  if (body.length === 0) return { kind: 'ok', text: `됨 · ${what} 0개` }
  const miss = missingKeys(body[0], keys)
  return miss.length ? { kind: 'shape', text: `빠진 칸: ${miss.join(', ')}` } : { kind: 'ok', text: `됨 · ${what} ${body.length}개` }
}
const objectOf = (keys: string[]) => (body: unknown): Result => {
  const miss = missingKeys(body, keys)
  return miss.length ? { kind: 'shape', text: `빠진 칸: ${miss.join(', ')}` } : { kind: 'ok', text: '됨' }
}

function checkWebSocket(): Promise<Result> {
  return new Promise((done) => {
    const url = new URL(`${API}/ws`, window.location.href)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    let ws: WebSocket
    try {
      ws = new WebSocket(url)
    } catch {
      return done({ kind: 'down', text: '연결을 만들지 못했어요' })
    }
    const t = setTimeout(() => {
      ws.close()
      done({ kind: 'missing', text: '3초 안에 연결되지 않았어요' })
    }, 3000)
    ws.onopen = () => {
      clearTimeout(t)
      ws.close()
      done({ kind: 'ok', text: '됨 · 연결 열림' })
    }
    ws.onerror = () => {
      clearTimeout(t)
      done({ kind: 'missing', text: '연결이 거절됐어요 (/api/ws 가 아직 없을 수 있어요)' })
    }
  })
}

const STEPS: Step[] = [
  {
    no: 1,
    title: '서버 켜짐',
    iface: 'GET /health (진단 상태 조회)',
    screen: null,
    auto: async () => judge(await getJson('/health'), () => ({ kind: 'ok', text: '됨 · 서버가 답해요' })),
    how: '서버를 켜고 이 화면의 "다시 확인"을 누르세요.',
  },
  {
    no: 2,
    title: '메뉴',
    iface: 'WEB-03 GET /menu',
    screen: { label: '테이블 태블릿 T1', path: '/table/3' },
    auto: async () => judge(await getJson('/menu'), listOf(['menu_id', 'name', 'price', 'is_available'], '메뉴')),
    how: '태블릿 첫 화면에 메뉴 카드가 보이면 됩니다.',
  },
  {
    no: 3,
    title: '테이블 목록',
    iface: 'GET /tables',
    screen: { label: '테이블 태블릿', path: '/table/3' },
    auto: async () => judge(await getJson('/tables'), listOf(['table_id', 'code', 'seats', 'status', 'visit_id'], '테이블')),
    how: '태블릿이 자기 테이블에 앉은 손님(visit_id)을 이걸로 찾습니다.',
  },
  {
    no: 4,
    title: '입구 접수',
    iface: 'WEB-01 POST /visits',
    screen: { label: '입구 키오스크 K1 → K2', path: '/kiosk' },
    how: '키오스크에서 "2명" → "2명으로 자리 찾기"를 눌러 K2 "N번 테이블로 안내할게요"가 뜨면 됩니다. (안내 로봇이 움직일 수 있어 자동으로 보내지 않아요)',
  },
  {
    no: 5,
    title: '방문 상태',
    iface: 'WEB-02 GET /visits/{visit_id}/status',
    screen: { label: '키오스크 K2~K4 · 태블릿 T3', path: '/kiosk' },
    auto: async ({ visitId }) => {
      if (!visitId) return { kind: 'idle' }
      return judge(
        await getJson(`/visits/${encodeURIComponent(visitId)}/status`),
        objectOf(['visit_id', 'status', 'table_id', 'guide', 'can_end', 'orders', 'version']),
      )
    },
    how: '4번 접수를 한 번 하면(손님이 있는 테이블이 생기면) 자동으로 확인할 수 있어요.',
  },
  {
    no: 6,
    title: '실시간 알림',
    iface: 'WebSocket /ws (상태 변경 구독)',
    screen: { label: '모든 화면', path: '/kiosk' },
    auto: () => checkWebSocket(),
    how: '없으면 화면이 처음 한 번만 받고 그 뒤로 바뀌지 않아요 (K2 → K4로 안 넘어감).',
  },
  {
    no: 7,
    title: '주문',
    iface: 'WEB-04 POST /orders',
    screen: { label: '테이블 태블릿 T1 → T2 → T3', path: '/table/3' },
    how: '손님이 앉은 테이블 태블릿에서 메뉴를 담고 "주문하기" → T3 주문 상태가 뜨면 됩니다.',
  },
  {
    no: 8,
    title: '이용 종료',
    iface: 'WEB-06 POST /visits/{visit_id}/end',
    screen: { label: '테이블 태블릿 T3 → T5', path: '/table/3' },
    how: '음식을 다 받은 뒤 T3 "이용 종료" → T5 확인창 → "이용해 주셔서 고마워요"가 뜨면 됩니다.',
  },
  {
    no: 9,
    title: '관리자 현황',
    iface: 'WEB-07 GET /admin/overview',
    screen: { label: '관리자 A1·A2·A3', path: '/admin' },
    auto: async () =>
      judge(await getJson('/admin/overview'), objectOf(['robots', 'tables', 'orders', 'tasks', 'alarms', 'ros_connected', 'version'])),
    how: '관리자 화면에서 "연결 안 됨"이 사라지고 로봇·테이블 상태가 보이면 됩니다.',
  },
  {
    no: 10,
    title: '관리자 조작',
    iface: 'WEB-08 POST /admin/operations · WEB-09 GET /admin/operations/{id}',
    screen: { label: '관리자 A1 · A2 · A3 버튼', path: '/admin' },
    how: 'A2 정리 대기 테이블의 "정리 완료 → 이용 가능"이 가장 안전한 첫 시험이에요. 성공하면 위쪽에 초록 알림이 떠요.',
  },
]

const BADGE: Record<Result['kind'], { text: string; bg: string; fg: string }> = {
  idle: { text: '화면에서 확인', bg: '#EEF0F3', fg: '#5C6370' },
  running: { text: '확인 중…', bg: '#EEF0F3', fg: '#5C6370' },
  ok: { text: '됨', bg: '#EAF7EF', fg: '#17703F' },
  shape: { text: '모양 다름', bg: '#FFF4DB', fg: '#8A5A00' },
  missing: { text: '아직 없음', bg: '#FFF1E7', fg: '#C2410C' },
  down: { text: '서버 꺼짐', bg: '#FDECEA', fg: '#B42318' },
}

export function ApiCheck() {
  const [results, setResults] = useState<Record<number, Result>>({})

  const runAll = useCallback(async () => {
    setResults(Object.fromEntries(STEPS.filter((s) => s.auto).map((s) => [s.no, { kind: 'running' }])))
    // 방문 상태 확인용: 손님이 있는 테이블의 visit_id
    const tables = await getJson('/tables')
    const visitId =
      Array.isArray(tables?.body) ? ((tables.body as { visit_id?: string | null }[]).find((t) => t.visit_id)?.visit_id ?? null) : null
    for (const s of STEPS) {
      if (!s.auto) continue
      const r = await s.auto({ visitId })
      setResults((prev) => ({ ...prev, [s.no]: r }))
    }
  }, [])

  useEffect(() => {
    void runAll()
  }, [runAll])

  const autoSteps = STEPS.filter((s) => s.auto)
  const okCount = autoSteps.filter((s) => results[s.no]?.kind === 'ok').length

  return (
    <main style={{ maxWidth: 880, margin: '0 auto', padding: '40px 16px 80px' }}>
      <a href="/" style={{ color: 'var(--c-text-sub)' }}>
        ← 화면 목록
      </a>
      <h1 style={{ fontSize: 28, fontWeight: 800, margin: '12px 0 8px' }}>백엔드 연결 점검</h1>
      <p style={{ margin: 0, color: 'var(--c-text-sub)', lineHeight: 1.7 }}>
        위에서부터 순서대로 붙이면 됩니다. 각 단계가 어떻게 보여야 하는지는 <b>목업에서 보기</b>로 미리 볼 수 있어요.
        <br />
        자동 확인 {okCount}/{autoSteps.length} 됨 · 백엔드 주소는 <code>frontend/.env</code>의 <code>BACKEND_URL</code>
      </p>
      <button
        onClick={() => void runAll()}
        style={{ margin: '16px 0 24px', height: 44, padding: '0 20px', border: 0, borderRadius: 12, background: 'var(--c-accent)', color: '#fff', fontWeight: 700 }}
      >
        다시 확인
      </button>

      <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 12 }}>
        {STEPS.map((s) => {
          const r = results[s.no] ?? { kind: 'idle' as const }
          const b = BADGE[r.kind]
          return (
            <li key={s.no} aria-label={`${s.no}단계 ${s.title}`} style={{ background: '#fff', borderRadius: 16, padding: '16px 20px', display: 'grid', gap: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ width: 28, height: 28, borderRadius: 14, background: 'var(--c-surface)', display: 'grid', placeItems: 'center', fontWeight: 800 }}>
                  {s.no}
                </span>
                <b style={{ fontSize: 17 }}>{s.title}</b>
                <code style={{ color: 'var(--c-text-sub)', fontSize: 13 }}>{s.iface}</code>
                <span style={{ marginLeft: 'auto', padding: '4px 10px', borderRadius: 999, background: b.bg, color: b.fg, fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap' }}>
                  {b.text}
                </span>
              </div>
              {'text' in r && <div style={{ color: b.fg, fontSize: 14 }}>{r.text}</div>}
              <div style={{ color: 'var(--c-text-sub)', fontSize: 14, lineHeight: 1.6 }}>{s.how}</div>
              {s.screen && (
                <div style={{ display: 'flex', gap: 12, fontSize: 14 }}>
                  <span style={{ color: 'var(--c-text-sub)' }}>{s.screen.label}:</span>
                  <a href={s.screen.path}>진짜 서버로 열기</a>
                  <a href={MOCK_BASE + s.screen.path}>목업에서 보기</a>
                </div>
              )}
            </li>
          )
        })}
      </ol>
      <p style={{ marginTop: 24, color: 'var(--c-text-sub)', fontSize: 14, lineHeight: 1.7 }}>
        주고받는 데이터의 칸 하나하나는 <code>frontend/src/api/contract.ts</code>(손님 화면)와 <code>adminContract.ts</code>(관리자)에,
        주소 표는 <code>frontend/README.md</code>의 "백엔드 연결"에 있어요.
      </p>
    </main>
  )
}
