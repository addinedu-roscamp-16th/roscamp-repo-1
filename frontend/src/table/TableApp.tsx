import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ApiError,
  getApi,
  newRequestKey,
  type DiningTable,
  type FrybotApi,
  type MenuItem,
  type VisitSnapshot,
} from '../api'
import c from '../components/customer.module.css'
import { Stage } from '../components/Stage'
import type { CartLine } from './format'
import { T1Menu, T2Confirm, T3Status, T4Arrived, T5EndDialog, TableEnded, TableTopBar } from './screens'

export const TABLE_W = 932
export const TABLE_H = 572
const TOAST_MS = 3000

type View = 'menu' | 'confirm' | 'status'

/**
 * 테이블 태블릿 (테이블 번호 고정). 흐름: T1 메뉴 → T2 확인 → T3 진행 상태 ⇄ T1 추가 주문.
 * 서빙 로봇이 오면(주문 ARRIVED) 어느 화면에서든 T4, 전달이 끝나면 원래 화면으로 돌아갑니다.
 *
 *  - 테이블의 현재 방문: 구독 { table_id } → dining_table.visit_id
 *  - 방문 상태·주문 진행: 구독 { visit_id } (WEB-02 스냅샷과 같은 모양)
 *  - 메뉴 WEB-03 · 주문 WEB-04 · 이용 종료 WEB-06
 */
export function TableApp({ tableId, api: injected }: { tableId: number; api?: FrybotApi }) {
  const api = useMemo(() => injected ?? getApi(), [injected])
  const [menu, setMenu] = useState<MenuItem[] | null>(null)
  const [table, setTable] = useState<DiningTable | null>(null)
  const [visit, setVisit] = useState<VisitSnapshot | null>(null)
  const [view, setView] = useState<View>('menu')
  const [cart, setCart] = useState<CartLine[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [endOpen, setEndOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [now, setNow] = useState(() => new Date())
  const orderKey = useRef<string | null>(null)
  const endKey = useRef<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .getMenu(tableId)
      .then((m) => alive && setMenu(m))
      .catch(() => alive && setToast('메뉴를 불러오지 못했어요. 직원을 불러 주세요'))
    return () => {
      alive = false
    }
  }, [api, tableId])

  useEffect(
    () =>
      api.subscribe([{ table_id: tableId }], (e) => {
        if (e.type === 'table') setTable(e.data)
      }),
    [api, tableId],
  )

  // 새 손님(새 방문)이 앉으면 처음 화면부터
  const visitId = table?.visit_id ?? null
  useEffect(() => {
    setVisit(null)
    setView('menu')
    setCart([])
    setError(null)
    setEndOpen(false)
    orderKey.current = null
    endKey.current = null
    if (!visitId) return
    let first = true
    return api.subscribe([{ visit_id: visitId }], (e) => {
      if (e.type !== 'visit') return
      setVisit(e.data)
      // 새로고침했을 때 주문이 이미 있으면 진행 상태부터
      if (first) {
        first = false
        if (e.data.orders.length > 0) setView('status')
      }
    })
  }, [api, visitId])

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(t)
  }, [toast])

  const orders = visit?.orders ?? []
  const arrived = orders.find((o) => o.status === 'ARRIVED') ?? null

  // T4: 음식이 도착하면 알림음
  const arrivedId = arrived?.order_id ?? null
  useEffect(() => {
    if (arrivedId) chime()
  }, [arrivedId])

  const setQty = (menuId: number, qty: number) => {
    orderKey.current = null // 담은 내용이 바뀌면 새 주문
    setCart((prev) => {
      const rest = prev.filter((l) => l.menu_id !== menuId)
      return qty > 0 ? [...rest, { menu_id: menuId, qty }].sort(byMenu(menu)) : rest
    })
  }

  const place = async () => {
    if (!visit || busy) return
    orderKey.current ??= newRequestKey()
    setBusy(true)
    setError(null)
    try {
      await api.createOrder({ visit_id: visit.visit_id, table_id: tableId, items: cart, request_key: orderKey.current })
      orderKey.current = null
      setCart([])
      setView('status')
    } catch (e) {
      const code = e instanceof ApiError ? e.code : 'UNKNOWN'
      const retrySame = code === 'RESULT_UNCONFIRMED' || code === 'NETWORK'
      if (!retrySame) orderKey.current = null
      setError(
        retrySame
          ? '주문이 들어갔는지 확인하지 못했어요. 한 번 더 눌러 주세요'
          : code === 'MENU_UNAVAILABLE'
            ? '품절된 메뉴가 있어요. 수정해 주세요'
            : '주문을 보내지 못했어요. 직원을 불러 주세요',
      )
    } finally {
      setBusy(false)
    }
  }

  const askEnd = () => {
    if (visit && !visit.can_end) {
      setToast('아직 받지 않은 음식이 있어요. 다 받은 뒤에 마칠 수 있어요')
      return
    }
    setEndOpen(true)
  }

  const endVisit = async () => {
    if (!visit) return
    endKey.current ??= newRequestKey()
    setBusy(true)
    try {
      const res = await api.endVisit(visit.visit_id, endKey.current)
      endKey.current = null
      setEndOpen(false)
      if (res.result === 'PENDING') setToast('종료를 확인하고 있어요. 직원이 곧 도와드릴게요')
    } catch {
      setToast('이용 종료를 처리하지 못했어요. 직원을 불러 주세요')
    } finally {
      setBusy(false)
    }
  }

  const callStaff = async () => {
    try {
      await api.callStaff('table', tableId)
      setToast('직원을 불렀어요. 잠시만 기다려 주세요')
    } catch {
      setToast('직원 호출에 실패했어요. 다시 눌러 주세요')
    }
  }

  const latest = orders[orders.length - 1]
  const ended = visit?.status === 'END_OF_USE' || table?.status === 'CLEANING'
  const empty = !ended && table != null && !visitId
  const shown: View = view === 'status' && !latest ? 'menu' : view

  let label = '메뉴'
  let body: ReactNode
  if (ended || empty) {
    label = ended ? '이용 종료' : '빈 자리'
    body = <TableEnded variant={ended ? 'ended' : 'empty'} />
  } else if (arrived) {
    label = '음식 도착'
    body = <T4Arrived order={arrived} />
  } else if (shown === 'confirm' && menu) {
    label = '주문 확인'
    body = (
      <T2Confirm
        tableId={tableId}
        menu={menu}
        cart={cart}
        busy={busy}
        error={error}
        onEdit={() => setView('menu')}
        onPlace={place}
      />
    )
  } else if (shown === 'status' && latest) {
    label = `주문 ${latest.order_id}`
    body = <T3Status order={latest} now={now} onMore={() => setView('menu')} onEnd={askEnd} />
  } else {
    body = (
      <T1Menu
        menu={menu}
        cart={cart}
        hasOrders={orders.length > 0}
        canOrder={visit != null}
        onChange={setQty}
        onNext={() => setView('confirm')}
        onStatus={() => setView('status')}
      />
    )
  }

  return (
    <Stage width={TABLE_W} height={TABLE_H}>
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <TableTopBar tableId={tableId} label={label} arrived={!!arrived && !ended} onCallStaff={callStaff} />
        {body}
        {endOpen && !ended && !arrived && (
          <T5EndDialog busy={busy} onKeep={() => setEndOpen(false)} onEnd={endVisit} />
        )}
        {toast && (
          <div className={c.toast} role="status">
            {toast}
          </div>
        )}
      </div>
    </Stage>
  )
}

function byMenu(menu: MenuItem[] | null) {
  const order = (id: number) => menu?.findIndex((m) => m.menu_id === id) ?? 0
  return (a: CartLine, b: CartLine) => order(a.menu_id) - order(b.menu_id)
}

/** 짧은 "딩동" 알림음. 소리를 낼 수 없는 환경이면 조용히 넘어갑니다. */
function chime() {
  try {
    const Ctx =
      window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctx) return
    const ctx = new Ctx()
    ;[880, 660].forEach((hz, i) => {
      const o = ctx.createOscillator()
      const g = ctx.createGain()
      o.frequency.value = hz
      const t = ctx.currentTime + i * 0.25
      g.gain.setValueAtTime(0.0001, t)
      g.gain.exponentialRampToValueAtTime(0.25, t + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.4)
      o.connect(g).connect(ctx.destination)
      o.start(t)
      o.stop(t + 0.45)
    })
    setTimeout(() => void ctx.close(), 1200)
  } catch {
    /* 소리 없이 진행 */
  }
}
