import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createTableApi, type CartLine, type MenuItem, type TableApi, type TableState } from '../api'
import c from '../components/customer.module.css'
import { Stage } from '../components/Stage'
import { T1Menu, T2Confirm, T3Status, T4Arrived, T5EndDialog, TableEnded, TableTopBar } from './screens'

export const TABLE_W = 932
export const TABLE_H = 572
const TOAST_MS = 3000

type View = 'menu' | 'confirm' | 'status'

/**
 * 테이블 태블릿. 흐름: T1 메뉴 → T2 확인 → T3 진행 상태 ⇄ T1 추가 주문.
 * 서빙 로봇이 오면 어느 화면에서든 T4로 바뀌고, 전달이 끝나면 원래 화면으로 돌아갑니다.
 * T3의 "이용 종료"는 T5 확인창을 띄웁니다.
 */
export function TableApp({ tableId, api: injected }: { tableId: string; api?: TableApi }) {
  const api = useMemo(() => injected ?? createTableApi(), [injected])
  const [menu, setMenu] = useState<MenuItem[] | null>(null)
  const [state, setState] = useState<TableState | null>(null)
  const [view, setView] = useState<View>('menu')
  const [cart, setCart] = useState<CartLine[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [endOpen, setEndOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [now, setNow] = useState(() => new Date())
  const firstState = useRef(true)

  useEffect(() => {
    let alive = true
    api
      .getMenu()
      .then((m) => alive && setMenu(m))
      .catch(() => alive && setToast('메뉴를 불러오지 못했어요. 직원을 불러 주세요'))
    return () => {
      alive = false
    }
  }, [api])

  useEffect(() => {
    firstState.current = true
    return api.watchTable(tableId, (st) => {
      setState(st)
      // 새로고침했을 때 주문이 이미 있으면 진행 상태부터 보여 줌
      if (firstState.current) {
        firstState.current = false
        if (st.orders.length > 0) setView('status')
      }
    })
  }, [api, tableId])

  // 이용 종료 뒤 다음 손님이 앉으면(세션이 다시 열리고 주문이 비면) 처음 화면으로
  const session = state?.session
  const prevSession = useRef(session)
  useEffect(() => {
    if (prevSession.current === 'ended' && session === 'active') {
      setView('menu')
      setCart([])
      setError(null)
    }
    prevSession.current = session
  }, [session])

  // 도착 예정 "약 N분 뒤"를 갱신
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(t)
  }, [toast])

  // T4: 음식이 도착하면 알림음
  const deliveryKey = state?.delivery ? state.delivery.orderId : null
  useEffect(() => {
    if (deliveryKey) chime()
  }, [deliveryKey])

  const setQty = (menuId: string, qty: number) =>
    setCart((prev) => {
      const rest = prev.filter((l) => l.menuId !== menuId)
      return qty > 0 ? [...rest, { menuId, qty }].sort(byMenu(menu)) : rest
    })

  const place = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.placeOrder(tableId, cart)
      setCart([])
      setView('status')
    } catch {
      setError('주문을 보내지 못했어요. 다시 눌러 주세요')
    } finally {
      setBusy(false)
    }
  }

  const endSession = async () => {
    setBusy(true)
    try {
      await api.endSession(tableId)
      setEndOpen(false)
    } catch {
      setToast('이용 종료를 처리하지 못했어요. 직원을 불러 주세요')
    } finally {
      setBusy(false)
    }
  }

  const callStaff = async () => {
    try {
      await api.callStaff(tableId)
      setToast('직원을 불렀어요. 잠시만 기다려 주세요')
    } catch {
      setToast('직원 호출에 실패했어요. 다시 눌러 주세요')
    }
  }

  const orders = state?.orders ?? []
  const latest = orders[orders.length - 1]
  const delivery = state?.delivery ?? null
  const ended = state?.session === 'ended'
  // 진행 상태로 가야 하는데 주문이 없으면 메뉴로
  const shown: View = view === 'status' && !latest ? 'menu' : view

  let label = '메뉴'
  let body: ReactNode
  if (ended) {
    label = '이용 종료'
    body = <TableEnded />
  } else if (delivery) {
    label = '음식 도착'
    body = <T4Arrived delivery={delivery} />
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
    label = `주문 ${latest.orderId}`
    body = <T3Status order={latest} now={now} onMore={() => setView('menu')} onEnd={() => setEndOpen(true)} />
  } else {
    body = (
      <T1Menu
        menu={menu}
        cart={cart}
        hasOrders={orders.length > 0}
        onChange={setQty}
        onNext={() => setView('confirm')}
        onStatus={() => setView('status')}
      />
    )
  }

  return (
    <Stage width={TABLE_W} height={TABLE_H}>
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <TableTopBar tableId={tableId} label={label} arrived={!!delivery && !ended} onCallStaff={callStaff} />
        {body}
        {endOpen && !ended && !delivery && (
          <T5EndDialog busy={busy} onKeep={() => setEndOpen(false)} onEnd={endSession} />
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
  const order = (id: string) => menu?.findIndex((m) => m.menuId === id) ?? 0
  return (a: CartLine, b: CartLine) => order(a.menuId) - order(b.menuId)
}

/** 짧은 "딩동" 알림음. 소리를 낼 수 없는 환경이면 조용히 넘어갑니다. */
function chime() {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
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
