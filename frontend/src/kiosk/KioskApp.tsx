import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  NoTableAvailableError,
  createKioskApi,
  type GuideStatus,
  type KioskApi,
  type PartySize,
  type TableAssignment,
} from '../api'
import { Stage } from '../components/Stage'
import c from '../components/customer.module.css'
import { TopBar } from './parts'
import { K1PartySize, K2TableAssigned, K3RobotWaiting, K4GuideStart } from './screens'

export const KIOSK_W = 932
export const KIOSK_H = 572
export const RETURN_SECONDS = 10
const TOAST_MS = 3000

type Phase =
  | { screen: 'K1' }
  | { screen: 'K2' | 'K3'; assignment: TableAssignment; status: GuideStatus | null }
  | { screen: 'K4'; assignment: TableAssignment; secondsLeft: number }

/**
 * 입구 키오스크. 흐름: K1 → K2 → K4, 로봇이 없으면 K2 → K3 → K4.
 * K4에서 10초가 지나거나 "처음으로"를 누르면 K1로 돌아갑니다.
 */
export function KioskApp({ api: injected }: { api?: KioskApi }) {
  const api = useMemo(() => injected ?? createKioskApi(), [injected])
  const [phase, setPhase] = useState<Phase>({ screen: 'K1' })
  const [selected, setSelected] = useState<PartySize | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const unsubscribe = useRef<(() => void) | null>(null)

  const stopWatching = () => {
    unsubscribe.current?.()
    unsubscribe.current = null
  }

  const reset = useCallback(() => {
    stopWatching()
    setPhase({ screen: 'K1' })
    setSelected(null)
    setBusy(false)
    setError(null)
  }, [])

  // 화면을 떠날 때 구독 정리
  useEffect(() => stopWatching, [])

  const onStatus = useCallback((assignment: TableAssignment, status: GuideStatus) => {
    setPhase((prev) => {
      if (prev.screen === 'K1' || prev.screen === 'K4') return prev
      if (status.state === 'robot_arrived') {
        return { screen: 'K4', assignment, secondsLeft: RETURN_SECONDS }
      }
      // 한 번 대기(K3)로 갔으면 로봇이 출발해도 K3에 머물다 도착 시 K4로
      const screen = status.state === 'queued' || prev.screen === 'K3' ? 'K3' : 'K2'
      return { screen, assignment, status }
    })
    if (status.state === 'robot_arrived') stopWatching()
  }, [])

  const submit = async () => {
    if (!selected || busy) return
    setBusy(true)
    setError(null)
    try {
      const assignment = await api.assignTable(selected)
      setPhase({ screen: 'K2', assignment, status: null })
      unsubscribe.current = api.watchGuide(assignment.assignmentId, (st) => onStatus(assignment, st))
    } catch (e) {
      setError(
        e instanceof NoTableAvailableError
          ? '지금은 맞는 자리가 없어요. 직원 호출을 눌러 주세요'
          : '자리를 찾지 못했어요. 잠시 후 다시 눌러 주세요',
      )
    } finally {
      setBusy(false)
    }
  }

  const goHome = () => {
    if (phase.screen === 'K2' || phase.screen === 'K3') {
      void api.cancelAssignment(phase.assignment.assignmentId).catch(() => {})
    }
    reset()
  }

  const callStaff = async () => {
    try {
      await api.callStaff(phase.screen === 'K1' ? 'party_over_4' : 'help')
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
          <K1PartySize selected={selected} busy={busy} error={error} onSelect={setSelected} onSubmit={submit} />
        )}
        {phase.screen === 'K2' && (
          <K2TableAssigned
            assignment={phase.assignment}
            status={phase.status?.state === 'robot_coming' ? phase.status : null}
            onHome={goHome}
          />
        )}
        {phase.screen === 'K3' && (
          <K3RobotWaiting assignment={phase.assignment} status={phase.status} onHome={goHome} />
        )}
        {phase.screen === 'K4' && (
          <K4GuideStart
            assignment={phase.assignment}
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
