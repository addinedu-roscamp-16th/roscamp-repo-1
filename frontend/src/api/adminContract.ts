/**
 * 관리자 PC(A1~A3) ↔ Web Service 데이터 계약.
 *
 * 기준 문서 (Confluence, 2026-11-20 설계 검토안):
 *   - 1) FryBot I/F 목록 — WEB-07 관리자 현황 조회, WEB-08 관리자 조작 요청, WEB-09 관리자 조작 결과 조회
 *   - 4) Logical Data Model — robot / task / incident / event_log 테이블, 관제용 뷰 v_table_board · v_robot_board
 *
 * 필드 구성은 문서에 없어 여기서 제안한 값입니다([제안]).
 * 위치는 ROS map 좌표(m, x 오른쪽, y 위쪽) — robot.pose_x/pose_y 그대로.
 */
import type { DiningTable, Order, TableId, TableStatus, VisitStatus } from './contract'

/* ── 로봇 (robot, v_robot_board) ── */

/** robot.state — AMR 레인 */
export type AmrState =
  | 'IDLE'
  | 'E_STOP'
  | 'TO_ENTRANCE'
  | 'GUIDING'
  | 'PAUSED'
  | 'ARRIVED'
  | 'RETURNING'
  | 'CHARGING'
  | 'TO_PICKUP'
  | 'QUEUED'
  | 'DOCKED'
  | 'SERVING'

/** robot.state — 로봇팔 Station 레인 */
export type ArmState =
  | 'IDLE'
  | 'E_STOP'
  | 'PICK_CHICKEN'
  | 'FRYING'
  | 'WAIT_TIMER'
  | 'LIFT_AND_DRAIN'
  | 'PICK_INGREDIENTS'
  | 'STIR_FRYING'
  | 'PLATING'
  | 'ON_HANDOFF'
  | 'RETRY'
  | 'LOADING'

export type CookType = 'FRY' | 'WOK'

interface RobotBase {
  /** ROS2 네임스페이스와 같음 (pinky1, cook_arm_a …) */
  robot_id: string
  /** 마지막 상태 보고 */
  last_seen_at: string
  /** 진행 중 임무 */
  task_id: string | null
  /** PAUSED 직전 상태 [제안] */
  hold_state: string | null
}

export interface AmrView extends RobotBase {
  type: 'AMR'
  state: AmrState
  pose: { x: number; y: number; yaw: number }
  battery_pct: number
  is_charging: boolean
  /** m/s [제안] */
  speed: number
  /** 남은 계획 경로 (m) [제안] — 지도에 선으로 그림 */
  path: [number, number][]
}

export interface ArmView extends RobotBase {
  type: 'ARM'
  cook_type: CookType
  state: ArmState
  /** 지금 조리 중인 것 [제안] */
  cook: {
    order_id: string
    name: string
    qty: number
    /** 1부터 */
    step: number
    steps: number
    remaining_sec: number
  } | null
}

export type RobotView = AmrView | ArmView

/* ── 임무 (task) ── */

export type TaskType = 'GUIDE' | 'COOK' | 'SERVE'

/** task.state — Service Workflow 레인. 완료는 finished_at 으로 표시 */
export type TaskState =
  | 'GUIDE_REQ'
  | 'GUIDE_PENDING'
  | 'GUIDE_EXCEPTION'
  | 'COOK_TASK'
  | 'SERVE_REQ'
  | 'SERVE_PENDING'
  | 'ON_HOLD'
  | 'RECOVERY_WAIT'
  | 'CHECK'
  | 'RESUME'
  | 'CANCEL_TASK'
  | 'REASSIGN'
  | 'CANCELED'

export interface AdminTask {
  task_id: string
  task_type: TaskType
  state: TaskState
  robot_id: string | null
  visit_id: string | null
  order_id: string | null
  table_id: TableId | null
  /** 안내 인원 (GUIDE) [제안] */
  party_size: number | null
  /** 받을 곳 (SERVE) [제안] */
  pickup: CookType | null
  created_at: string
  assigned_at: string | null
  finished_at: string | null
  /** 이 임무 동안 로봇 상태가 바뀐 시각 (event_log) [제안] — 임무 단계 표시에 씀 */
  robot_states: { state: string; at: string }[]
}

/* ── 테이블 (v_table_board) ── */

export interface AdminTable extends DiningTable {
  visit: {
    visit_id: string
    party_size: number
    status: VisitStatus
    checked_in_at: string
    seated_at: string | null
    ended_at: string | null
  } | null
}

export interface AdminOrder extends Order {
  visit_id: string
}

/* ── 알람 (incident + 경고·정보) ── */

export type AlarmLevel = 'ERROR' | 'WARN' | 'INFO'

export interface Alarm {
  alarm_id: string
  level: AlarmLevel
  /** robot_id, 또는 'SYSTEM' */
  source: string
  /** 오류 코드 (SR-036) 예: E-ARM-021 */
  code: string
  message: string
  occurred_at: string
  /** 관리자가 읽음 */
  acked: boolean
  /** 오류·관리자 중단이면 incident 기록 */
  incident: {
    incident_id: string
    source: 'DEVICE_ERROR' | 'ADMIN_STOP'
    /** 장치 부위 [제안] 예: "적재 · 전달" */
    device_part: string | null
    task_id: string | null
    order_id: string | null
    table_id: TableId | null
    /** 실패한 작업 단계(당시 robot.state) */
    failed_state: string | null
    /** 사람이 읽는 실패 단계 [제안] 예: "적재 3/4 · 용기 파지" */
    failed_step: string | null
    /** 재시도 전 확인할 것 [제안] */
    hint: string | null
    admin_choice: 'RETRY' | 'STOP' | null
    result: 'RESUME' | 'REASSIGN' | 'CANCELED' | null
    resolved_at: string | null
  } | null
}

/* ── WEB-07 GET /admin/overview ── */

export interface AdminOverview {
  server_time: string
  /** Web Service ↔ ROS2 연결 [제안] */
  ros_connected: boolean
  robots: RobotView[]
  tables: AdminTable[]
  /** 진행 중 + 최근 완료 */
  orders: AdminOrder[]
  /** 진행 중 + 대기 */
  tasks: AdminTask[]
  /** 최근 알람 (새것부터) */
  alarms: Alarm[]
  version: number
}

/* ── WEB-08 POST /admin/operations · WEB-09 GET /admin/operations/{operation_id} ── */

export type OperationKind =
  | 'PAUSE' // 로봇 일시 중단
  | 'RESUME' // 다시 진행
  | 'REASSIGN' // 진행 중 임무를 다른 AMR에 (SR-034)
  | 'E_STOP' // 비상 정지
  | 'SET_TABLE_STATUS' // 테이블 상태 변경 (SR-029·031)
  | 'INCIDENT_RETRY' // 오류 처리: 재시도
  | 'INCIDENT_STOP' // 오류 처리: 작업 취소
  | 'ACK_ALARM' // 알람 읽음

export interface OperationRequest {
  kind: OperationKind
  /** robot_id · table_id · alarm_id */
  target_id: string
  params?: { status?: TableStatus }
  request_key: string
}

export interface OperationAccepted {
  operation_id: string
  /** ACCEPTED 수락 · CONFLICT 다른 상태와 충돌(바로 거절) · PENDING 확인 중 */
  result: 'ACCEPTED' | 'CONFLICT' | 'PENDING'
  reason: string | null
}

export interface OperationStatus {
  operation_id: string
  /** 실제 조작 결과 · 실패 · 불명 */
  status: 'PENDING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN'
  message: string | null
}

/* ── 운영 이력 (event_log) · Replay — I/F 목록에 없음 [제안] ── */

export interface EventLogRow {
  log_id: string
  entity: 'VISIT' | 'TABLE' | 'ORDER' | 'TASK' | 'ROBOT' | 'INCIDENT'
  entity_id: string
  from_state: string | null
  to_state: string | null
  actor: 'ENTRANCE_UI' | 'TABLE_UI' | 'ADMIN_UI' | 'ORDER_MANAGER' | 'WORKFLOW' | 'AI_SERVER' | 'AMR' | 'ARM'
  message: string
  /** TASK면 task_type 등 */
  detail: { task_type?: TaskType; alarm_id?: string } | null
  created_at: string
}

export interface EventQuery {
  from: string
  to: string
}

/** GET /admin/replay?from&to — 초당 1장 [제안] */
export interface ReplayFrame {
  t: string
  robots: { robot_id: string; x: number; y: number; state: string }[]
}

/* ── 화면이 쓰는 API ── */

export interface AdminApi {
  /** WEB-07 */
  getOverview(): Promise<AdminOverview>
  /** WEB-08 */
  requestOperation(req: OperationRequest): Promise<OperationAccepted>
  /** WEB-09 */
  getOperation(operationId: string): Promise<OperationStatus>
  /** 상태 변경 구독 {admin: true} — 최대 2 Hz로 현황 전체를 보냄. 연결 상태도 알려 줌 */
  subscribeOverview(onData: (o: AdminOverview) => void, onConnection?: (ok: boolean) => void): () => void
  /** GET /admin/events?from&to [제안] */
  getEvents(q: EventQuery): Promise<EventLogRow[]>
  /** GET /admin/replay?from&to [제안] */
  getReplay(q: EventQuery): Promise<ReplayFrame[]>
}
