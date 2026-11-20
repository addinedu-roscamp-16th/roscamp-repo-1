/**
 * 관리자 PC(A1~A3) ↔ Web Service 데이터 계약.
 * 기준은 저장소의 **api/openapi.yaml** (WEB-07/08/09, 이력·Replay). 여기 타입은 자동 생성(schema.gen.ts)을 다시 내보낸 것입니다.
 * 위치는 ROS map 좌표(m, x 오른쪽, y 위쪽) — robot.pose_x/pose_y 그대로.
 */
import type { components } from './schema.gen'

type S = components['schemas']

/* ── 로봇 ── */
export type AmrState = S['AmrState']
export type ArmState = S['ArmState']
export type CookType = S['CookType']
export type AmrView = S['AmrView']
export type ArmView = S['ArmView']
export type RobotView = S['RobotView']

/* ── 임무 · 테이블 · 주문 ── */
export type TaskType = S['TaskType']
export type TaskState = S['TaskState']
export type AdminTask = S['AdminTask']
export type AdminTable = S['AdminTable']
export type AdminOrder = S['AdminOrder']

/* ── 알람 ── */
export type AlarmLevel = S['AlarmLevel']
export type Alarm = S['Alarm']

/* ── WEB-07 · WEB-08 · WEB-09 ── */
export type AdminOverview = S['AdminOverview']
export type OperationKind = S['OperationKind']
export type OperationRequest = S['OperationRequest']
export type OperationAccepted = S['OperationAccepted']
export type OperationStatus = S['OperationStatus']

/* ── 이력 · Replay [제안] ── */
export type EventLogRow = S['EventLogRow']
export type ReplayFrame = S['ReplayFrame']
export interface EventQuery {
  from: string
  to: string
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
