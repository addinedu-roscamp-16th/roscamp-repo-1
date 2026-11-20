/**
 * 화면(Web Browser) ↔ Web Service 데이터 계약.
 *
 * 기준 문서 (Confluence, 2026-11-20 설계 검토안):
 *   - 1) FryBot I/F 목록 — WEB-01~09, 상태 변경 구독(WebSocket)
 *   - 4) Logical Data Model — 상태 이름 (visit / dining_table / orders / task / robot)
 *
 * 문서가 "확인 필요"로 남긴 필드명·형식은 여기서 제안한 값입니다(아래 [제안] 표시).
 * 문서가 확정되면 이 파일만 고치면 됩니다.
 */

/* ── 기준 정보 ── */

/** dining_table.table_id — 맵 구성도의 1~6번 */
export type TableId = number

/** dining_table.status */
export type TableStatus = 'AVAILABLE' | 'ASSIGNED' | 'IN_USE' | 'CLEANING'

/** GET /tables 한 줄 [제안: 필드 구성] */
export interface DiningTable {
  table_id: TableId
  /** dining_table.code, 예 "T5" */
  code: string
  seats: number
  status: TableStatus
  /** 이 테이블의 진행 중 방문 (ASSIGNED·IN_USE일 때) [제안] */
  visit_id: string | null
}

/** GET /menu 한 줄 (WEB-03) */
export interface MenuItem {
  menu_id: number
  name: string
  /** 원. menu.price는 DB 제안 단계라 없을 수 있음 → 화면은 금액 표시를 보류 */
  price: number | null
  is_available: boolean
  /** [제안] */
  image_url?: string | null
}

/* ── 방문 (visit) ── */

/** visit.status */
export type VisitStatus = 'CHECK_IN' | 'WAITING' | 'ASSIGNED' | 'IN_USE' | 'END_OF_USE'

/** POST /visits 요청 (WEB-01) */
export interface CreateVisitRequest {
  party_size: number
  request_key: string
}

/** POST /visits 응답 (WEB-01) */
export interface CreateVisitResponse {
  visit_id: string
  status: 'WAITING' | 'ASSIGNED'
  table_id: TableId | null
  queue_no: number | null
}

/**
 * 안내 진행 (task GUIDE + 안내 AMR의 robot.state) [제안: 묶음 형식]
 *  - PENDING     : 가용 AMR 없음 (task.state GUIDE_PENDING) → K3
 *  - TO_ENTRANCE : AMR이 입구로 오는 중 → K2
 *  - GUIDING     : AMR이 입구에 와서 안내 시작 → K4
 *  - ARRIVED     : 테이블 도착 (착석)
 *  - EXCEPTION   : 손님을 놓침 (GUIDE_EXCEPTION)
 */
export interface GuideProgress {
  state: 'PENDING' | 'TO_ENTRANCE' | 'GUIDING' | 'ARRIVED' | 'EXCEPTION'
  robot_id: string | null
  /** PENDING일 때 안내 대기 순번 */
  queue_position: number | null
  /** 남은 예상 시간(초). 모르면 null */
  eta_sec: number | null
  /** TO_ENTRANCE 진행률 0~1. 모르면 null */
  progress: number | null
}

/** orders.status */
export type OrderStatus =
  | 'ORDERED'
  | 'COOKING'
  | 'READY'
  | 'SERVING'
  | 'ARRIVED'
  | 'COMPLETED'
  | 'ON_HOLD'
  | 'CANCELED'

export interface OrderItem {
  order_item_id: string
  menu_id: number
  name: string
  qty: number
  /** order_item.ready_at — 서빙 준비 완료(인계대) 시각 */
  ready_at: string | null
}

export interface Order {
  order_id: string
  table_id: TableId
  status: OrderStatus
  items: OrderItem[]
  created_at: string
  /** 도착 예정 시각. ETA는 범위 밖(DB 제안)이라 없으면 null [제안] */
  eta_at: string | null
  /**
   * ARRIVED 단계의 전달 진행 (모바일 로봇팔 TransferObject) [제안]
   * STOPPED: 정차 확인, TRANSFERRING: 테이블로 옮기는 중, DONE: 전달 완료
   */
  delivery_step: 'STOPPED' | 'TRANSFERRING' | 'DONE' | null
}

/** GET /visits/{visit_id}/status 응답 (WEB-02) [제안: 필드 구성] */
export interface VisitSnapshot {
  visit_id: string
  status: VisitStatus
  party_size: number
  table_id: TableId | null
  queue_no: number | null
  guide: GuideProgress | null
  /** 이용 종료 버튼을 받을 수 있는지 (미전달 주문이 없을 때 등) */
  can_end: boolean
  orders: Order[]
  /** 관측 버전 — 값이 클수록 최신 */
  version: number
}

/* ── 주문 (WEB-04) ── */

export interface CreateOrderRequest {
  visit_id: string
  table_id: TableId
  items: { menu_id: number; qty: number }[]
  request_key: string
}

export interface CreateOrderResponse {
  order_id: string
  status: 'ORDERED'
}

/* ── 방문 종료 (WEB-06) ── */

export interface EndVisitResponse {
  /** ACCEPTED: 종료 접수, PENDING: 확인 근거가 없어 보류 [제안] */
  result: 'ACCEPTED' | 'PENDING'
  /** 식기 회수 필요 여부 */
  collect_required: boolean
}

/* ── 상태 변경 구독 (WebSocket) [제안: 메시지 형식] ── */

export type Topic = { visit_id: string } | { table_id: TableId }

/** 브라우저 → 서버 */
export interface SubscribeMessage {
  type: 'subscribe'
  topics: Topic[]
}

/** 서버 → 브라우저. version이 건너뛰거나 거꾸로 오면 스냅샷을 다시 조회합니다. */
export type ServerEvent =
  | { type: 'visit'; version: number; data: VisitSnapshot }
  | { type: 'table'; version: number; data: DiningTable }

/* ── 오류 ── */

/** WEB-01 오류 코드 + 공통 */
export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'VISIT_NOT_ALLOWED'
  | 'REQUEST_KEY_CONFLICT'
  | 'RESULT_UNCONFIRMED'
  | 'MENU_UNAVAILABLE'
  | 'NETWORK'
  | 'UNKNOWN'

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
