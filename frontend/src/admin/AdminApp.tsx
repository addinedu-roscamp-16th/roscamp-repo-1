import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { getAdminApi, newRequestKey, type AdminApi, type AdminOverview } from '../api'
import { Stage } from '../components/Stage'
import { AlarmsReplay } from './AlarmsReplay'
import { Ctx, EMPTY_OVERVIEW, opKey, useAdmin, type AdminCtx, type RunOp } from './context'
import { C, hhmmss } from './labels'
import { Monitoring } from './Monitoring'
import s from './admin.module.css'
import { TablesOrders } from './TablesOrders'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * 관리자 PC (A1 통합 관제 · A2 테이블·주문 · A3 알람·이력).
 * 현황은 WEB-07 + 상태 변경 구독으로 받고, 조작은 WEB-08로 보낸 뒤 WEB-09로 결과를 확인합니다.
 */
export function AdminApp({ api: injected, pollMs = 300 }: { api?: AdminApi; pollMs?: number }) {
  const api = useMemo(() => injected ?? getAdminApi(), [injected])
  const [ov, setOv] = useState<AdminOverview | null>(null)
  const [connected, setConnected] = useState(true)
  /** 처음 연결을 몇 초 기다렸는데도 현황이 없음 */
  const [waitedLong, setWaitedLong] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [toast, setToast] = useState<{ text: string; tone: 'ok' | 'error'; id: number } | null>(null)
  const [busyKeys, setBusyKeys] = useState<ReadonlySet<string>>(new Set())
  /** 결과를 모르는 조작은 같은 요청 키로 다시 보냄 */
  const pendingKeys = useRef(new Map<string, string>())

  useEffect(() => api.subscribeOverview(setOv, setConnected), [api])
  useEffect(() => {
    const t = setTimeout(() => setWaitedLong(true), 4000)
    return () => clearTimeout(t)
  }, [])
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3500)
    return () => clearTimeout(t)
  }, [toast])

  const notify = useCallback<AdminCtx['notify']>((text, tone = 'ok') => setToast({ text, tone, id: Date.now() }), [])

  const run = useCallback<RunOp>(
    async (req, doneText) => {
      const k = opKey(req)
      const key = pendingKeys.current.get(k) ?? newRequestKey()
      pendingKeys.current.set(k, key)
      setBusyKeys((b) => new Set(b).add(k))
      const finish = (ok: boolean, text: string, keep = false) => {
        if (!keep) pendingKeys.current.delete(k)
        setBusyKeys((b) => {
          const n = new Set(b)
          n.delete(k)
          return n
        })
        notify(text, ok ? 'ok' : 'error')
        return ok
      }
      try {
        const acc = await api.requestOperation({ ...req, request_key: key })
        if (acc.result === 'CONFLICT') return finish(false, acc.reason ?? '다른 상태와 겹쳐 처리하지 못했어요')
        for (let i = 0; i < 20; i++) {
          await sleep(pollMs)
          const st = await api.getOperation(acc.operation_id)
          if (st.status === 'SUCCEEDED') return finish(true, doneText)
          if (st.status === 'FAILED') return finish(false, st.message ?? '처리하지 못했어요')
          if (st.status === 'UNKNOWN') break
        }
        return finish(false, '결과를 확인하지 못했어요. 다시 누르면 같은 요청으로 확인해요', true)
      } catch {
        return finish(false, '서버에 닿지 않았어요. 다시 눌러 주세요', true)
      }
    },
    [api, notify, pollMs],
  )

  const ctx = useMemo<AdminCtx>(
    () => ({ api, ov: ov ?? EMPTY_OVERVIEW, hasData: ov != null, connected, now, run, notify, busy: (r) => busyKeys.has(opKey(r)) }),
    [api, ov, connected, now, run, notify, busyKeys],
  )

  return (
    <Stage width={1440} height={900} backdrop={C.bg} frameStyle={{ borderRadius: 0, background: C.bg }}>
      <Ctx.Provider value={ctx}>
        <div className={s.root}>
          <Header />
          <div className={s.body}>
            <Routes>
              <Route index element={<Monitoring />} />
              <Route path="tables" element={<TablesOrders />} />
              <Route path="alarms" element={<AlarmsReplay />} />
            </Routes>
          </div>
          <ConnectionNotice hasData={ov != null} connected={connected} waitedLong={waitedLong} lastAt={ov?.server_time ?? null} />
          {toast && (
            <div key={toast.id} role={toast.tone === 'error' ? 'alert' : 'status'} className={`${s.toast} ${toast.tone === 'error' ? s.toastError : ''}`}>
              {toast.text}
            </div>
          )}
        </div>
      </Ctx.Provider>
    </Stage>
  )
}

function Header() {
  const { connected, now, ov } = useAdmin()
  const path = useLocation().pathname
  const replay = path.endsWith('/alarms')
  const tables = path.endsWith('/tables')
  const ros = connected && (ov?.ros_connected ?? false)
  const nav = ({ isActive }: { isActive: boolean }) => `${s.navLink} ${isActive ? s.navOn : ''}`
  return (
    <header className={s.header}>
      <div className={s.brand}>
        OneTeam <span>관제</span>
      </div>
      <nav aria-label="관제 메뉴" className={s.nav}>
        <NavLink to="/admin" end className={nav}>
          통합 관제
        </NavLink>
        <NavLink to="/admin/tables" className={nav}>
          테이블 · 주문
        </NavLink>
        <NavLink to="/admin/alarms" className={nav}>
          알람 · 이력
        </NavLink>
      </nav>
      <div className={s.headRight}>
        {!tables && (
          <>
            <span className={s.muted}>모드</span>
            <span className={replay ? s.modeReplay : s.modeLive}>{replay ? 'REPLAY' : 'LIVE'}</span>
          </>
        )}
        {!replay && (
          <>
            <span className={s.muted} style={{ marginLeft: 6 }}>
              ROS2
            </span>
            <span className={ros ? s.rosOk : s.rosBad}>{ros ? '연결됨' : '끊김'}</span>
            <span className={s.muted} style={{ marginLeft: 6 }}>
              {hhmmss(now)}
            </span>
          </>
        )}
        <span className={s.user}>admin</span>
      </div>
    </header>
  )
}

/** 서버와 연결이 안 될 때 무엇을 확인할지 알려 줌. 연결되면 사라짐 */
function ConnectionNotice({ hasData, connected, waitedLong, lastAt }: { hasData: boolean; connected: boolean; waitedLong: boolean; lastAt: string | null }) {
  if (hasData && connected) return null
  if (!hasData && connected && !waitedLong)
    return (
      <div role="status" className={s.notice}>
        <b>서버에 연결하는 중…</b>
      </div>
    )
  return (
    <div role="alert" className={`${s.notice} ${s.noticeBad}`}>
      <b>{hasData ? `서버와 연결이 끊겼어요 · ${hhmmss(lastAt ?? Date.now())}에 받은 정보를 보여 주는 중` : '백엔드 서버에 연결되지 않았어요'}</b>
      <span>
        서버가 켜져 있는지, <code>frontend/.env</code>의 <code>BACKEND_URL</code> 주소가 맞는지 확인해 주세요. 연결되면 화면이 저절로 채워져요.
      </span>
      {!hasData && (
        <Link to="/" className={s.link}>
          첫 화면에서 가짜 데이터로 바꾸기
        </Link>
      )}
    </div>
  )
}
