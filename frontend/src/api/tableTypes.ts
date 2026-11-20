// 테이블 태블릿(T1~T5) ↔ 백엔드 데이터 계약

export interface MenuItem {
  menuId: string
  name: string
  /** 원 단위. 시안은 [가격] 자리표시라 가짜 API에 예시 값을 넣었습니다. */
  price: number
  imageUrl?: string
}

export interface CartLine {
  menuId: string
  qty: number
}

/** 메뉴 한 줄의 진행 상태 (T3 오른쪽 문구) */
export type ItemStatus = 'queued' | 'cooking' | 'ready' | 'serving' | 'served'

export interface OrderItem {
  menuId: string
  name: string
  qty: number
  status: ItemStatus
}

/** T3 단계 표시: 접수 → 조리 중 → 서빙 → 완료 */
export type OrderStage = 'received' | 'cooking' | 'serving' | 'done'

export interface Order {
  /** 예: "ORD-0012" */
  orderId: string
  tableId: string
  items: OrderItem[]
  stage: OrderStage
  placedAt: string
  /** 도착 예정 시각(ISO). ML 예측이 들어오기 전에는 규칙 기반 값 */
  etaAt: string | null
}

/** T4 음식 도착 진행: 정차 확인 → 로봇팔이 테이블로 옮김 → 전달 완료 */
export type DeliveryStep = 'arrived' | 'transferring' | 'done'

export interface Delivery {
  orderId: string
  /** 이번에 가져온 메뉴 이름 */
  itemNames: string[]
  step: DeliveryStep
}

/** 테이블 상태 스냅숏. 백엔드는 WebSocket으로 바뀔 때마다 통째로 보냅니다. */
export interface TableState {
  tableId: string
  /** active: 이용 중, ended: 이용 종료(정리 대기) */
  session: 'active' | 'ended'
  orders: Order[]
  /** 서빙 로봇이 테이블에 와 있으면 값이 있음 (T4) */
  delivery: Delivery | null
}

export interface TableApi {
  getMenu(): Promise<MenuItem[]>
  placeOrder(tableId: string, lines: CartLine[]): Promise<Order>
  watchTable(tableId: string, onState: (s: TableState) => void): () => void
  endSession(tableId: string): Promise<void>
  callStaff(tableId: string): Promise<void>
}
