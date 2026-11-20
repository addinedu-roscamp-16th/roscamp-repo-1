import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, getApi, newRequestKey, type FrybotApi, type GuideProgress } from '../api'
import { tableSpec } from '../api/storeLayout'
import c from '../components/customer.module.css'
import { Stage } from '../components/Stage'
import type { PartySize, Seat } from './format'
import { TopBar } from './parts'
import { K1PartySize, K2TableAssigned, K3RobotWaiting, K4GuideStart } from './screens'

export const KIOSK_W = 932
export const KIOSK_H = 572
export const RETURN_SECONDS = 10
const TOAST_MS = 3000

type Phase =
  | { screen: 'K1' }
  | { screen: 'K2' | 'K3'; seat: Seat; visitId: string; guide: GuideProgress | null }
  | { screen: 'K4'; seat: Seat; secondsLeft: number }

/**
 * 입구 키오스크. 흐름: K1 → K2 → K4, 안내 로봇이 없으면 K2 → K3 → K4.
 *  - 접수: WEB-01 POST /visits  (ASSIGNED면 배정, WAITING이면 빈 테이블 없음)
 *  - 안내 진행: 상태 변경 구독(WebSocket)의 visit.guide
 * K4에서 10초가 지나거나 "처음으로"를 누르면 K1로 돌아갑니다.
 */
export function KioskApp({ api: injected }: { api?: FrybotApi }) {
  const api = useMemo(() => injected ?? getApi(), [injected])
  const [phase, setPhase] = useState<Phase>({ screen: 'K1' })
  const [selected, setSelected] = useState<PartySize | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const unsubscribe = useRef<(() => void) | null>(null)
  // 같은 접수를 다시 보낼 때(응답 유실·결과 불명)는 같은 요청 키를 씀 (WEB-01)
  const pendingKey = useRef<{ party: PartySize; key: string } | null>(null)

  const stopWatching = () => {
    unsubscribe.current?.()
    unsubscribe.current = null
  }

  const reset = useCallback(() => {
    stopWatching()
    pendingKey.current = null
    setPhase({ screen: 'K1' })
    setSelected(null)
    setBusy(false)
    setError(null)
  }, [])

  useEffect(() => stopWatching, [])

  const onGuide = useCallback((seat: Seat, visitId: string, guide: GuideProgress | null) => {
    setPhase((prev) => {
      if (prev.screen === 'K1' || prev.screen === 'K4') return prev
      if (guide && (guide.state === 'GUIDING' || guide.state === 'ARRIVED')) {
        stopWatching()
        return { screen: 'K4', seat, secondsLeft: RETURN_SECONDS }
      }
      // 한 번 대기(K3)로 갔으면 로봇이 출발해도 K3에 머물다 도착하면 K4로
      const screen = guide?.state === 'PENDING' || prev.screen === 'K3' ? 'K3' : 'K2'
      return { screen, seat, visitId, guide }
    })
  }, [])

  const submit = async () => {
    if (!selected || busy) return
    if (pendingKey.current?.party !== selected) pendingKey.current = { party: selected, key: newRequestKey() }
    setBusy(true)
    setError(null)
    try {
      const res = await api.createVisit({ party_size: selected, request_key: pendingKey.current.key })
      pendingKey.current = null
      if (res.status === 'WAITING' || res.table_id == null) {
        setSelected(null)
        setError(
          `지금은 빈 자리가 없어요. 대기 ${res.queue_no ?? '-'}번으로 접수했어요. 자리가 나면 직원이 불러 드릴게요`,
        )
        return
      }
      const seat: Seat = {
        tableId: res.table_id,
        seats: tableSpec(res.table_id)?.seats ?? selected,
        partySize: selected,
      }
      setPhase({ screen: 'K2', seat, visitId: res.visit_id, guide: null })
      unsubscribe.current = api.subscribe([{ visit_id: res.visit_id }], (e) => {
        if (e.type === 'visit') onGuide(seat, res.visit_id, e.data.guide)
      })
    } catch (e) {
      const code = e instanceof ApiError ? e.code : 'UNKNOWN'
      if (code !== 'RESULT_UNCONFIRMED' && code !== 'NETWORK') pendingKey.current = null
      setError(
        code === 'RESULT_UNCONFIRMED' || code === 'NETWORK'
          ? '접수 결과를 확인하지 못했어요. 한 번 더 눌러 주세요'
          : code === 'VISIT_NOT_ALLOWED'
            ? '지금은 접수할 수 없어요. 직원 호출을 눌러 주세요'
            : '자리를 찾지 못했어요. 잠시 후 다시 눌러 주세요',
      )
    } finally {
      setBusy(false)
    }
  }

  const callStaff = async () => {
    try {
      await api.callStaff('kiosk')
      setToast('직원을 불렀어요. 잠시만 기다려 주세요')
    } catch {
      setToast('직원 호출에 실패했어요. 다시 눌러 주세요')
    }
  }

  // K4: 1초마다 줄어들다가 0이면 첫 화면으로
  const k4Left = phase.screen === 'K4' ? phase.secondsLeft : null
  useEffect(() => {
    if (k4Left === null) return
    if (k4Left <= 0) {
      reset()
      return
    }
    const t = setTimeout(
      () => setPhase((p) => (p.screen === 'K4' ? { ...p, secondsLeft: p.secondsLeft - 1 } : p)),
      1000,
    )
    return () => clearTimeout(t)
  }, [k4Left, reset])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(t)
  }, [toast])

  const step = phase.screen === 'K1' ? 1 : phase.screen === 'K4' ? 3 : 2

  return (
    <Stage width={KIOSK_W} height={KIOSK_H}>
      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', height: '100%' }}>
        <TopBar step={step} onCallStaff={callStaff} />
        {phase.screen === 'K1' && (
          <K1PartySize
            selected={selected}
            busy={busy}
            error={error}
            onSelect={(n) => {
              setSelected(n)
              setError(null)
            }}
            onSubmit={submit}
          />
        )}
        {phase.screen === 'K2' && <K2TableAssigned assignment={phase.seat} guide={phase.guide} onHome={reset} />}
        {phase.screen === 'K3' && <K3RobotWaiting assignment={phase.seat} guide={phase.guide} onHome={reset} />}
        {phase.screen === 'K4' && (
          <K4GuideStart
            assignment={phase.seat}
            secondsLeft={phase.secondsLeft}
            totalSeconds={RETURN_SECONDS}
            onHome={reset}
          />
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
