// 프론트엔드 ↔ 백엔드(FastAPI) 데이터 계약.
// 백엔드를 붙일 때 이 타입과 같은 모양의 JSON을 주고받으면 됩니다.

/** 키오스크에서 고를 수 있는 인원 (5명 이상은 직원 호출) */
export type PartySize = 1 | 2 | 3 | 4

export const PARTY_SIZES: readonly PartySize[] = [1, 2, 3, 4]

/** POST /api/kiosk/assignments 응답 */
export interface TableAssignment {
  assignmentId: string
  /** 예: "T5" */
  tableId: string
  /** 테이블 좌석 수 (예: 4인석 → 4) */
  seats: number
  partySize: PartySize
}

/**
 * 안내 로봇 진행 상황. 백엔드는 WebSocket
 * /api/kiosk/assignments/{assignmentId}/guide 로 이 값을 계속 보내 줍니다.
 */
export type GuideStatus =
  /** 안내 로봇이 입구로 오는 중 (K2) */
  | { state: 'robot_coming'; robotId: string; etaSec: number; progress: number }
  /** 비어 있는 로봇이 없어 대기 중 (K3) */
  | { state: 'queued'; queuePosition: number; etaSec: number }
  /** 로봇이 입구에 도착함 (K4) */
  | { state: 'robot_arrived'; robotId: string }

export type StaffCallReason = 'party_over_4' | 'help'

export class NoTableAvailableError extends Error {
  constructor() {
    super('no_table_available')
    this.name = 'NoTableAvailableError'
  }
}

export interface KioskApi {
  /** 인원에 맞는 테이블을 배정합니다. 빈 자리가 없으면 NoTableAvailableError. */
  assignTable(partySize: PartySize): Promise<TableAssignment>
  /** 안내 상황을 구독합니다. 반환 함수를 부르면 구독을 끊습니다. */
  watchGuide(assignmentId: string, onStatus: (s: GuideStatus) => void): () => void
  /** 손님이 "처음으로"를 눌러 배정을 취소합니다. */
  cancelAssignment(assignmentId: string): Promise<void>
  callStaff(reason: StaffCallReason): Promise<void>
}
