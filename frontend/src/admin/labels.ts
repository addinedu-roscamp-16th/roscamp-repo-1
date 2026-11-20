import type {
  AdminOrder,
  AdminOverview,
  AdminTask,
  Alarm,
  AmrView,
  ArmView,
  CookType,
  EventLogRow,
  RobotView,
  TableStatus,
} from '../api'

/* ── 이름 ── */

/** pinky1 → AMR-1, cook_arm_a → ARM-1 */
export function robotName(id: string) {
  if (id === 'SYSTEM') return '시스템'
  const n = id.match(/(\d+)$/)?.[1]
  if (id.startsWith('pinky') && n) return `AMR-${n}`
  if (id === 'cook_arm_a') return 'ARM-1'
  if (id === 'cook_arm_b') return 'ARM-2'
  return id
}
export const COOK_NAME: Record<CookType, string> = { FRY: '튀김', WOK: '웍' }
export const PICKUP_NAME: Record<CookType, string> = { FRY: '튀김 받는 곳', WOK: '볶음밥 받는 곳' }
export const armTitle = (a: ArmView) => `${COOK_NAME[a.cook_type]} 로봇팔`
export const taskNo = (id: string) => `M-${id.padStart(3, '0')}`

/* ── 색 ── */

export const C = {
  bg: '#0F1218',
  panel: '#171B24',
  raised: '#1E2330',
  line: '#2A3142',
  line2: '#3A4560',
  text: '#E7EAF0',
  sub: '#C9CFDA',
  muted: '#A3ACBD',
  blue: '#8AB8FF',
  blueBg: '#16264A',
  green: '#5BE3A0',
  greenBg: '#123524',
  amber: '#F5B942',
  amberBg: '#3A2E12',
  red: '#FF8A78',
  redBg: '#3B1512',
  gray: '#E7EAF0',
  grayBg: '#2A3142',
  primary: '#2F6FEB',
  danger: '#C62828',
} as const

/** 지도의 경로·로봇 색 (시안 Map3D) */
export const ROUTE = { pick: '#F59E0B', serve: '#22C55E', guide: '#8B5CF6', back: '#9CA3AF', idle: '#9CA3AF', error: '#EF4444' }
export type RouteKind = keyof typeof ROUTE

export type Tone = 'blue' | 'green' | 'amber' | 'red' | 'gray'
export const toneStyle = (t: Tone) =>
  ({
    blue: { background: C.blueBg, color: C.blue },
    green: { background: C.greenBg, color: C.green },
    amber: { background: C.amberBg, color: C.amber },
    red: { background: C.redBg, color: C.red },
    gray: { background: C.grayBg, color: C.gray },
  })[t]

/* ── AMR ── */

export function amrKind(r: AmrView, task: AdminTask | null): RouteKind {
  if (r.state === 'E_STOP') return 'error'
  if (r.state === 'RETURNING') return 'back'
  if (['TO_PICKUP', 'QUEUED', 'DOCKED'].includes(r.state)) return 'pick'
  if (r.state === 'SERVING') return 'serve'
  if (['TO_ENTRANCE', 'GUIDING'].includes(r.state)) return 'guide'
  if (task?.task_type === 'GUIDE') return 'guide'
  if (task?.task_type === 'SERVE') return 'serve'
  return 'idle'
}

const AMR_STATE: Record<AmrView['state'], [string, Tone]> = {
  IDLE: ['대기', 'gray'],
  CHARGING: ['충전', 'gray'],
  TO_ENTRANCE: ['안내', 'blue'],
  GUIDING: ['안내', 'blue'],
  ARRIVED: ['도착', 'green'],
  RETURNING: ['복귀', 'gray'],
  TO_PICKUP: ['픽업', 'amber'],
  QUEUED: ['픽업 대기', 'amber'],
  DOCKED: ['적재', 'amber'],
  SERVING: ['서빙', 'green'],
  PAUSED: ['일시 중단', 'amber'],
  E_STOP: ['비상 정지', 'red'],
}
const ARM_STATE: Record<ArmView['state'], string> = {
  IDLE: '대기',
  E_STOP: '비상 정지',
  PICK_CHICKEN: '바스켓 투입',
  FRYING: '튀김 중',
  WAIT_TIMER: '타이머 대기',
  LIFT_AND_DRAIN: '건져 기름 빼기',
  PICK_INGREDIENTS: '재료 투입',
  STIR_FRYING: '볶는 중',
  PLATING: '담기',
  ON_HANDOFF: '받는 곳에 놓기',
  RETRY: '다시 시도',
  LOADING: '재료 준비',
}
export const ARM_STEPS: Record<CookType, ArmView['state'][]> = {
  FRY: ['PICK_CHICKEN', 'FRYING', 'WAIT_TIMER', 'LIFT_AND_DRAIN', 'ON_HANDOFF'],
  WOK: ['PICK_INGREDIENTS', 'STIR_FRYING', 'PLATING', 'ON_HANDOFF'],
}

export function stateChip(r: RobotView): [string, Tone] {
  if (r.type === 'AMR') {
    const [label, tone] = AMR_STATE[r.state]
    if (r.state === 'ARRIVED') return [label, 'green']
    return [label, tone]
  }
  if (r.state === 'E_STOP') return ['비상 정지', 'red']
  return r.state === 'IDLE' ? ['대기', 'gray'] : ['조리 중', 'green']
}
export const armStateText = (s: ArmView['state']) => ARM_STATE[s]

/** 이력에 쓰는 상태 이름 (로봇·주문·테이블·임무) */
export function stateWord(entity: EventLogRow['entity'], st: string | null): string {
  if (!st) return '—'
  if (entity === 'ROBOT') return (AMR_STATE as Record<string, [string, Tone]>)[st]?.[0] ?? (ARM_STATE as Record<string, string>)[st] ?? st
  if (entity === 'ORDER') return orderText({ status: st } as AdminOrder)
  if (entity === 'TABLE') return (TABLE_STATUS as Record<string, [string, Tone]>)[st]?.[0] ?? st
  return TASK_STATE[st] ?? st
}
const TASK_STATE: Record<string, string> = {
  GUIDE_REQ: '안내 수행',
  GUIDE_PENDING: '안내 대기',
  GUIDE_EXCEPTION: '안내 예외',
  COOK_TASK: '조리',
  SERVE_REQ: '서빙 수행',
  SERVE_PENDING: '서빙 대기',
  ON_HOLD: '보류',
  RECOVERY_WAIT: '복구 대기',
  CHECK: '확인',
  RESUME: '재개',
  CANCEL_TASK: '취소 중',
  REASSIGN: '재할당',
  CANCELED: '취소',
  IN_USE: '이용 중',
  END_OF_USE: '이용 종료',
  ASSIGNED: '배정',
}
export const TASK_TYPE: Record<string, string> = { GUIDE: '안내', COOK: '조리', SERVE: '서빙' }

/** 대상 목록 아래 줄: 무엇을 하는지 */
export function amrDoing(r: AmrView, task: AdminTask | null, ov: AdminOverview): string {
  if (r.state === 'E_STOP') return task ? `${tName(task)} 중 정지 · 복구 대기` : '비상 정지 · 복구 대기'
  if (r.state === 'PAUSED') return task ? `${tName(task)} · 일시 중단` : '일시 중단'
  if (!task) {
    if (r.state === 'RETURNING') return '충전대로 복귀 중'
    if (r.state === 'CHARGING' || r.is_charging) return `충전대 대기 · 충전 중`
    return '충전대 대기'
  }
  if (task.task_type === 'GUIDE') {
    if (r.state === 'TO_ENTRANCE') return `입구로 이동 · ${task.table_id}번 ${task.party_size}명`
    if (r.state === 'RETURNING') return `${task.table_id}번 안내 끝 · 복귀 중`
    return `${task.table_id}번 안내 · 손님 ${task.party_size}명 동행`
  }
  const o = ov.orders.find((x) => x.order_id === task.order_id)
  const what = o ? `${o.order_id} ${itemsText(o)}` : (task.order_id ?? '')
  if (r.state === 'QUEUED') return `받는 곳 대기 · ${what}`
  if (r.state === 'TO_PICKUP' || r.state === 'DOCKED') return `${what} 받으러 감`
  if (r.state === 'RETURNING') return `${task.table_id}번 서빙 끝 · 복귀 중`
  return `${task.table_id}번 서빙 · ${what}`
}
const tName = (t: AdminTask) => `${t.table_id}번 ${t.task_type === 'GUIDE' ? '안내' : '서빙'}`

export function amrTarget(r: AmrView, task: AdminTask | null): string {
  if (r.state === 'RETURNING' || !task) return `충전대 ${r.robot_id.replace(/\D/g, '') || ''}`.trim()
  if (task.task_type === 'GUIDE' && r.state === 'TO_ENTRANCE') return '입구 · 손님 맞이'
  if (task.task_type === 'SERVE' && ['TO_PICKUP', 'QUEUED', 'DOCKED'].includes(r.state))
    return task.pickup ? PICKUP_NAME[task.pickup] : '받는 곳'
  return `${task.table_id}번 정차 위치`
}

/** 임무 단계 목록과 지금 단계 */
export function taskSteps(task: AdminTask, r: AmrView | null, order: AdminOrder | null) {
  const serve = task.task_type === 'SERVE'
  const steps = serve
    ? [
        { label: `${task.pickup ? PICKUP_NAME[task.pickup] : '받는 곳'} 이동`, states: ['TO_PICKUP', 'QUEUED'] },
        { label: '적재 확인', states: ['DOCKED'] },
        { label: '서빙 이동', states: ['SERVING'] },
        { label: '도착 · 정차 확인', states: ['ARRIVED'] },
        { label: '로봇팔 전달', states: [] as string[] },
        { label: '복귀 · 대기 위치', states: ['RETURNING'] },
      ]
    : [
        { label: '입구로 이동', states: ['TO_ENTRANCE'] },
        { label: '손님 동행 안내', states: ['GUIDING'] },
        { label: '테이블 도착 · 착석', states: ['ARRIVED'] },
        { label: '복귀 · 대기 위치', states: ['RETURNING'] },
      ]
  const live = r?.state === 'PAUSED' || r?.state === 'E_STOP' ? (r.hold_state ?? r.state) : r?.state
  let cur = steps.findIndex((s) => s.states.includes(live ?? ''))
  if (serve && live === 'ARRIVED' && order && (order.delivery_step === 'TRANSFERRING' || order.delivery_step === 'DONE')) cur = 4
  // 단계별 마친 시각: 다음 단계 상태로 처음 바뀐 시각
  const firstAt = (states: string[]) => task.robot_states.find((x) => states.includes(x.state))?.at ?? null
  return steps.map((s, i) => ({
    label: s.label,
    status: cur < 0 ? 'todo' : i < cur ? 'done' : i === cur ? 'now' : 'todo',
    at: i < cur ? (firstAt(steps[i + 1]?.states ?? []) ?? firstAt(s.states)) : null,
  })) as { label: string; status: 'done' | 'now' | 'todo'; at: string | null }[]
}

/* ── 주문 ── */

export const itemsText = (o: AdminOrder) => o.items.map((i) => `${i.name} ${i.qty}`).join(', ')

export function orderText(o: AdminOrder): string {
  switch (o.status) {
    case 'ORDERED':
      return '접수'
    case 'COOKING':
      return '조리 중'
    case 'READY':
      return '서빙 대기'
    case 'SERVING':
      return '서빙 중'
    case 'ARRIVED':
      return '전달 중'
    case 'COMPLETED':
      return '완료'
    case 'ON_HOLD':
      return '보류'
    case 'CANCELED':
      return '취소'
  }
}

/** 주문 항목 하나의 단계 (A2 오른쪽 칩) */
export function itemChip(o: AdminOrder, ready: boolean): [string, Tone] {
  if (o.status === 'CANCELED') return ['취소', 'gray']
  if (o.status === 'ON_HOLD') return ['보류', 'red']
  if (o.status === 'COMPLETED') return ['완료', 'gray']
  if (o.status === 'SERVING' || o.status === 'ARRIVED') return ['서빙', 'blue']
  if (ready) return ['서빙 준비', 'amber']
  if (o.status === 'ORDERED') return ['접수', 'gray']
  return ['조리', 'green']
}

/* ── 테이블 ── */

export const TABLE_STATUS: Record<TableStatus, [string, Tone]> = {
  AVAILABLE: ['이용 가능', 'gray'],
  ASSIGNED: ['안내 중', 'blue'],
  IN_USE: ['이용 중', 'green'],
  CLEANING: ['정리 대기', 'gray'],
}

/* ── 알람·이력 ── */

export const LEVEL: Record<Alarm['level'], [string, Tone]> = {
  ERROR: ['오류', 'red'],
  WARN: ['경고', 'amber'],
  INFO: ['정보', 'gray'],
}

export type EventCategory = 'order' | 'guide' | 'charge' | 'error' | 'table'
export const CATEGORY: Record<EventCategory, { label: string; color: string }> = {
  order: { label: '주문·서빙', color: '#22C55E' },
  guide: { label: '안내', color: '#5B9BFF' },
  charge: { label: '충전', color: '#F59E0B' },
  error: { label: '오류', color: '#EF4444' },
  table: { label: '테이블', color: '#A3ACBD' },
}
export function eventCategory(e: EventLogRow): EventCategory {
  if (e.entity === 'INCIDENT') return 'error'
  if (e.entity === 'VISIT') return 'guide'
  if (e.entity === 'TABLE') return 'table'
  if (e.entity === 'TASK') return e.detail?.task_type === 'GUIDE' ? 'guide' : 'order'
  if (e.entity === 'ROBOT') {
    if (e.to_state === 'CHARGING') return 'charge'
    if (e.to_state === 'E_STOP') return 'error'
    if (['TO_ENTRANCE', 'GUIDING'].includes(e.to_state ?? '')) return 'guide'
  }
  return 'order'
}

/* ── 시간 ── */

export const hhmm = (iso: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
export const hhmmss = (t: number | string) => {
  const d = new Date(t)
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':')
}
export const mmss = (sec: number) => `${Math.floor(Math.max(0, sec) / 60)}:${String(Math.floor(Math.max(0, sec) % 60)).padStart(2, '0')}`
export const minutesSince = (iso: string | null, now: number) =>
  iso ? Math.max(0, Math.floor((now - Date.parse(iso)) / 60_000)) : 0
