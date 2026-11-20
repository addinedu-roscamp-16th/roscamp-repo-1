import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { getAdminApi, newRequestKey, type AdminApi, type AdminOverview } from '../api'
import { Stage } from '../components/Stage'
import { AlarmsReplay } from './AlarmsReplay'
import { Ctx, opKey, useAdmin, type AdminCtx, type RunOp } from './context'
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
  const [now, setNow] = useState(() => Date.now())
  const [toast, setToast] = useState<{ text: string; tone: 'ok' | 'error'; id: number } | null>(null)
  const [busyKeys, setBusyKeys] = useState<ReadonlySet<string>>(new Set())
  /** 결과를 모르는 조작은 같은 요청 키로 다시 보냄 */
  const pendingKeys = useRef(new Map<string, string>())

  useEffect(() => api.subscribeOverview(setOv, setConnected), [api])
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
    () => ({ api, ov, connected, now, run, notify, busy: (r) => busyKeys.has(opKey(r)) }),
    [api, ov, connected, now, run, notify, busyKeys],
  )

  return (
    <Stage width={1440} height={900} backdrop={C.bg} frameStyle={{ borderRadius: 0, background: C.bg }}>
      <Ctx.Provider value={ctx}>
        <div className={s.root}>
          <Header />
          <div className={s.body}>
            {!ov ? (
              <p className={s.loading}>현황을 불러오는 중…</p>
            ) : (
              <Routes>
                <Route index element={<Monitoring />} />
                <Route path="tables" element={<TablesOrders />} />
                <Route path="alarms" element={<AlarmsReplay />} />
              </Routes>
            )}
          </div>
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
