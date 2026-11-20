/**
 * 화면(Web Browser) ↔ Web Service 데이터 계약.
 *
 * 데이터 모양은 저장소의 **api/openapi.yaml** 이 기준이고, 여기 타입은 거기서 자동 생성한 것(schema.gen.ts)을
 * 화면 코드에서 쓰기 편한 이름으로 다시 내보낸 것입니다. 모양을 바꿀 때는 openapi.yaml 을 고치고
 * `npm run gen:api` 를 실행하세요. (이 파일에서 직접 모양을 바꾸지 않습니다)
 */
import type { components } from './schema.gen'

type S = components['schemas']

/* ── 기준 정보 ── */
export type TableId = S['TableId']
export type TableStatus = S['TableStatus']
export type DiningTable = S['DiningTable']
export type MenuItem = S['MenuItem']

/* ── 방문 ── */
export type VisitStatus = S['VisitStatus']
export type CreateVisitRequest = S['CreateVisitRequest']
export type CreateVisitResponse = S['CreateVisitResponse']
export type GuideProgress = S['GuideProgress']
export type VisitSnapshot = S['VisitSnapshot']
export type EndVisitResponse = S['EndVisitResponse']

/* ── 주문 ── */
export type OrderStatus = S['OrderStatus']
export type OrderItem = S['OrderItem']
export type Order = S['Order']
export type CreateOrderRequest = S['CreateOrderRequest']
export type CreateOrderResponse = S['CreateOrderResponse']

/* ── 상태 변경 구독 (WebSocket /ws) ── */
/** 손님 화면이 구독하는 대상 (방문 하나 또는 테이블 하나) */
export type Topic = Exclude<S['Topic'], { admin: true }>
export interface SubscribeMessage {
  type: 'subscribe'
  topics: S['Topic'][]
}
/** 서버 → 브라우저. version이 건너뛰거나 거꾸로 오면 스냅샷을 다시 조회합니다. */
export type ServerEvent = S['ServerEvent']

/* ── 오류 ── */

/** 서버가 보내는 오류 코드(openapi.yaml ApiErrorCode) + 화면에서만 쓰는 NETWORK·UNKNOWN */
export type ApiErrorCode = S['ApiErrorCode'] | 'NETWORK' | 'UNKNOWN'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  constructor(code: ApiErrorCode, status = 0) {
    super(code)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/* ── 화면이 쓰는 API ── */

export interface FrybotApi {
  /** WEB-01 POST /visits */
  createVisit(req: CreateVisitRequest): Promise<CreateVisitResponse>
  /** WEB-02 GET /visits/{visit_id}/status */
  getVisit(visitId: string): Promise<VisitSnapshot>
  /** WEB-03 GET /menu */
  getMenu(tableId?: TableId): Promise<MenuItem[]>
  /** WEB-04 POST /orders */
  createOrder(req: CreateOrderRequest): Promise<CreateOrderResponse>
  /** WEB-06 POST /visits/{visit_id}/end */
  endVisit(visitId: string, requestKey: string): Promise<EndVisitResponse>
  /** GET /tables */
  getTables(): Promise<DiningTable[]>
  /**
   * 상태 변경 구독. 연결·재연결 때는 스냅샷을 먼저 한 번 보내 줍니다(누락 복원).
   * 반환 함수를 부르면 구독을 끊습니다.
   */
  subscribe(topics: Topic[], onEvent: (e: ServerEvent) => void): () => void
  /**
   * 직원 호출. I/F 목록에 아직 없음 → POST /staff-calls [제안]
   */
  callStaff(source: 'kiosk' | 'table', tableId?: TableId): Promise<void>
}

/** 요청 키: 버튼 확정 1회마다 새로 만들고, 같은 요청을 다시 보낼 때는 그대로 씁니다. */
export function newRequestKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}
