import {
  NoTableAvailableError,
  type GuideStatus,
  type KioskApi,
  type PartySize,
  type TableAssignment,
} from './types'

/** 시안 기준 매장 테이블 (좌석 수는 예시 값) */
export const MOCK_TABLES = [
  { id: 'T1', seats: 2 },
  { id: 'T2', seats: 2 },
  { id: 'T3', seats: 4 },
  { id: 'T4', seats: 4 },
  { id: 'T5', seats: 4 },
  { id: 'T6', seats: 6 },
] as const

export interface MockOptions {
  /** false면 비어 있는 로봇이 없어 대기(K3)부터 시작합니다. */
  robotAvailable?: boolean
  /** 시뮬레이션 1단계 간격(ms). 테스트에서는 짧게 씁니다. */
  tickMs?: number
  /** 이미 손님이 있는 테이블 */
  occupied?: string[]
}

const ROBOT_ETA_SEC = 30
const ETA_STEP_SEC = 5
const QUEUE_START = 2
const QUEUE_WAIT_PER_PERSON_SEC = 30

/** 서버 없이 화면 흐름을 확인하기 위한 가짜 API */
export function createMockKioskApi(opts: MockOptions = {}): KioskApi {
  const robotAvailable = opts.robotAvailable ?? true
  const tickMs = opts.tickMs ?? 1000
  const occupied = new Set(opts.occupied ?? [])
  const assignments = new Map<string, TableAssignment>()
  let seq = 0

  return {
    async assignTable(partySize: PartySize) {
      await delay(Math.min(400, tickMs))
      const table = [...MOCK_TABLES]
        .filter((t) => t.seats >= partySize && !occupied.has(t.id))
        // 좌석이 가장 딱 맞는 테이블, 같으면 번호가 큰(입구에 가까운) 테이블부터 — 시안: 4명 → T5
        .sort((a, b) => a.seats - b.seats || b.id.localeCompare(a.id))[0]
      if (!table) throw new NoTableAvailableError()
      occupied.add(table.id)
      const a: TableAssignment = {
        assignmentId: `mock-${++seq}`,
        tableId: table.id,
        seats: table.seats,
        partySize,
      }
      assignments.set(a.assignmentId, a)
      return a
    },

    watchGuide(_assignmentId, onStatus) {
      const steps: GuideStatus[] = []
      if (!robotAvailable) {
        for (let q = QUEUE_START; q >= 1; q--) {
          steps.push({ state: 'queued', queuePosition: q, etaSec: q * QUEUE_WAIT_PER_PERSON_SEC })
        }
      }
      for (let eta = ROBOT_ETA_SEC; eta > 0; eta -= ETA_STEP_SEC) {
        steps.push({
          state: 'robot_coming',
          robotId: 'guide-1',
          etaSec: eta,
          progress: 1 - eta / ROBOT_ETA_SEC,
        })
      }
      steps.push({ state: 'robot_arrived', robotId: 'guide-1' })

      let i = 0
      onStatus(steps[i++])
      const timer = setInterval(() => {
        onStatus(steps[i++])
        if (i >= steps.length) clearInterval(timer)
      }, tickMs)
      return () => clearInterval(timer)
    },

    async cancelAssignment(assignmentId) {
      const a = assignments.get(assignmentId)
      if (a) occupied.delete(a.tableId)
      assignments.delete(assignmentId)
    },

    async callStaff() {
      await delay(Math.min(200, tickMs))
    },
  }
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}
