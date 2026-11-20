import type {
  AdminApi,
  AdminOrder,
  AdminOverview,
  AdminTable,
  AdminTask,
  Alarm,
  AmrState,
  ArmState,
  CookType,
  EventLogRow,
  OperationAccepted,
  OperationRequest,
  OperationStatus,
  ReplayFrame,
} from './adminContract'
import type { TableId } from './contract'
import {
  GREET,
  PICKUPS,
  TABLES,
  homeOf,
  roadPath,
  toMap,
  type Pt,
} from './storeLayout'

/**
 * 관리자 화면용 가짜 매장. 손님 도착 → 안내 → 주문 → 조리 → 서빙 → 이용 종료 → 정리를
 * 0.5초 단위로 흉내 내고, 관리자 조작(WEB-08)을 받아 처리합니다.
 * 화면을 열면 지난 시간을 미리 돌려 두어 처음부터 매장이 돌아가는 모습과 이력이 보입니다.
 */

const STEP = 500
const AMR_IDS = ['pinky1', 'pinky2', 'pinky3']
const SPEED = 18 // cm/s (0.18 m/s)
const GUIDE_SPEED = 12

const MENU: Record<number, { name: string; cook: CookType }> = {
  1: { name: '치킨', cook: 'FRY' },
  2: { name: '볶음밥', cook: 'WOK' },
}
const ARM_STEPS: Record<CookType, [ArmState, number][]> = {
  FRY: [
    ['PICK_CHICKEN', 4000],
    ['FRYING', 24000],
    ['WAIT_TIMER', 4000],
    ['LIFT_AND_DRAIN', 4000],
    ['ON_HANDOFF', 3000],
  ],
  WOK: [
    ['PICK_INGREDIENTS', 4000],
    ['STIR_FRYING', 20000],
    ['PLATING', 4000],
    ['ON_HANDOFF', 3000],
  ],
}
const ARM_IDS: Record<CookType, string> = { FRY: 'cook_arm_a', WOK: 'cook_arm_b' }
const ASSIGN_ORDER: TableId[] = [5, 6, 1, 2, 4, 3]
/** 받는 곳이 막혔을 때 기다리는 칸 (layout.py STANDBY_NODES) */
const WAIT_SPOT: Record<CookType, Pt> = { FRY: [157, 6], WOK: [157, 94] }
const MOVING: AmrState[] = ['TO_ENTRANCE', 'GUIDING', 'TO_PICKUP', 'SERVING', 'RETURNING']

interface Amr {
  id: string
  pos: Pt
  yaw: number
  path: Pt[]
  speed: number
  state: AmrState
  hold: AmrState | null
  battery: number
  taskId: string | null
  waitUntil: number
  /** 정차 재시도 한 번 했음 */
  retried?: boolean
}

interface Job {
  orderId: string
  itemId: string
  taskId: string
  name: string
  qty: number
  step: number
  stepLeft: number
}

interface Arm {
  id: string
  cook: CookType
  state: ArmState
  hold: ArmState | null
  job: Job | null
  queue: Job[]
}

interface Task extends AdminTask {
  /** SERVE: 아직 들르지 않은 받는 곳 */
  pickupsLeft: CookType[]
  reassignedFrom: string | null
}

interface Op {
  req: OperationRequest
  status: OperationStatus
}

export interface SimOptions {
  /** 시뮬레이션 시작 시각(ms) */
  start: number
  seed?: number
  /** 이 시각 이후 처음 적재할 때 그리퍼 오류를 냄 */
  errorsAt?: number[]
  /** 손님 도착 간격(ms) [최소, 최대] */
  arrivalEvery?: [number, number]
}

function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const iso = (t: number) => new Date(t).toISOString()
const pad = (n: number, w: number) => String(n).padStart(w, '0')

export function createSim(opts: SimOptions) {
  const rand = rng(opts.seed ?? 7)
  const between = (a: number, b: number) => a + rand() * (b - a)
  const [arrMin, arrMax] = opts.arrivalEvery ?? [35_000, 70_000]
  const errorsAt = [...(opts.errorsAt ?? [])].sort((a, b) => a - b)

  let now = opts.start
  let version = 0
  const seq = { task: 0, order: 0, visit: 0, alarm: 0, log: 0, op: 0 }
  let nextArrival = now + 3000

  const amrs: Amr[] = AMR_IDS.map((id, i) => ({
    id,
    pos: homeOf(id),
    yaw: 0,
    path: [],
    speed: 0,
    state: 'IDLE',
    hold: null,
    battery: [92, 85, 88][i],
    taskId: null,
    waitUntil: 0,
  }))
  const arms: Arm[] = (['FRY', 'WOK'] as CookType[]).map((cook) => ({
    id: ARM_IDS[cook],
    cook,
    state: 'IDLE',
    hold: null,
    job: null,
    queue: [],
  }))
  const tables: AdminTable[] = TABLES.map((t) => ({
    table_id: t.id,
    code: `T${t.id}`,
    seats: t.seats,
    status: 'AVAILABLE',
    visit_id: null,
    visit: null,
  }))
  const orders: AdminOrder[] = []
  const tasks: Task[] = []
  const alarms: Alarm[] = []
  const events: EventLogRow[] = []
  const frames: ReplayFrame[] = []
  const ops = new Map<string, Op>()
  const opQueue: Op[] = []
  /** 방문별 다음 행동 시각 */
  const visitPlan = new Map<string, { orderAt: number | null; orders: number; endAt: number | null }>()
  const cleaningSince = new Map<TableId, number>()
  /** ON_HOLD 직전 주문 상태 (재시도하면 되돌림) */
  const orderHold = new Map<string, AdminOrder['status']>()

  /* ── 기록 ── */

  function log(
    entity: EventLogRow['entity'],
    id: string,
    from: string | null,
    to: string | null,
    actor: EventLogRow['actor'],
    message: string,
    detail: EventLogRow['detail'] = null,
  ) {
    events.push({
      log_id: String(++seq.log),
      entity,
      entity_id: id,
      from_state: from,
      to_state: to,
      actor,
      message,
      detail,
      created_at: iso(now),
    })
  }

  function raise(a: Omit<Alarm, 'alarm_id' | 'occurred_at' | 'acked'>) {
    const alarm: Alarm = { ...a, alarm_id: `AL-${pad(++seq.alarm, 4)}`, occurred_at: iso(now), acked: false }
    alarms.push(alarm)
    if (a.level === 'ERROR')
      log('INCIDENT', alarm.alarm_id, null, 'OPEN', a.source.startsWith('cook') ? 'ARM' : 'AMR', `${a.code} ${a.message}`, {
        alarm_id: alarm.alarm_id,
      })
    return alarm
  }

  const taskOf = (id: string | null) => (id ? (tasks.find((t) => t.task_id === id) ?? null) : null)
  const orderOf = (id: string | null) => (id ? (orders.find((o) => o.order_id === id) ?? null) : null)
  const tableOf = (id: TableId | null) => tables.find((t) => t.table_id === id) ?? null

  function setAmr(r: Amr, state: AmrState) {
    if (r.state === state) return
    log('ROBOT', r.id, r.state, state, 'AMR', `${r.id} ${r.state} → ${state}`)
    r.state = state
    taskOf(r.taskId)?.robot_states.push({ state, at: iso(now) })
  }

  function setTask(t: Task, state: Task['state'], finished = false) {
    if (t.state !== state)
      log('TASK', t.task_id, t.state, state, 'WORKFLOW', `${t.task_type} ${t.state} → ${state}`, { task_type: t.task_type })
    t.state = state
    if (finished) t.finished_at = iso(now)
  }

  function setOrder(o: AdminOrder, status: AdminOrder['status'], actor: EventLogRow['actor'] = 'ORDER_MANAGER') {
    if (o.status === status) return
    if (status === 'ON_HOLD') orderHold.set(o.order_id, o.status)
    log('ORDER', o.order_id, o.status, status, actor, `${o.order_id} ${o.status} → ${status}`)
    o.status = status
  }

  function setTable(t: AdminTable, status: AdminTable['status'], actor: EventLogRow['actor'], message: string) {
    if (t.status === status) return
    log('TABLE', String(t.table_id), t.status, status, actor, message)
    t.status = status
    if (status === 'CLEANING') cleaningSince.set(t.table_id, now)
    if (status === 'AVAILABLE') {
      t.visit = null
      t.visit_id = null
    }
  }

  function newTask(p: Partial<Task> & Pick<Task, 'task_type' | 'state'>): Task {
    const t: Task = {
      task_id: String(++seq.task),
      robot_id: null,
      visit_id: null,
      order_id: null,
      table_id: null,
      party_size: null,
      pickup: null,
      created_at: iso(now),
      assigned_at: null,
      finished_at: null,
      robot_states: [],
      pickupsLeft: [],
      reassignedFrom: null,
      ...p,
    }
    tasks.push(t)
    log('TASK', t.task_id, null, t.state, 'WORKFLOW', `${t.task_type} 임무 생성`, { task_type: t.task_type })
    return t
  }

  /* ── 이동 ── */

  function go(r: Amr, dest: Pt, state: AmrState, speed = SPEED) {
    const p = roadPath(r.pos, dest)
    if (p.length && p[0][0] === r.pos[0] && p[0][1] === r.pos[1]) p.shift()
    r.path = p
    r.speed = speed
    setAmr(r, state)
  }

  /** 한 단계 이동. 도착하면 true */
  function move(r: Amr, dt: number) {
    let left = (r.speed * dt) / 1000
    while (left > 0 && r.path.length) {
      const [tx, ty] = r.path[0]
      const dx = tx - r.pos[0]
      const dy = ty - r.pos[1]
      const d = Math.hypot(dx, dy)
      if (d > 0) r.yaw = Math.atan2(-dy, dx)
      if (d <= left) {
        r.pos = [tx, ty]
        r.path.shift()
        left -= d
        r.battery = Math.max(5, r.battery - d * 0.01)
      } else {
        r.pos = [r.pos[0] + (dx / d) * left, r.pos[1] + (dy / d) * left]
        r.battery = Math.max(5, r.battery - left * 0.01)
        left = 0
      }
    }
    return r.path.length === 0
  }

  const stopOf = (id: TableId | null) => TABLES.find((t) => t.id === id)?.stop ?? GREET
  const atHome = (r: Amr) => {
    const h = homeOf(r.id)
    return Math.hypot(h[0] - r.pos[0], h[1] - r.pos[1]) < 1
  }
  const dockedAt = (cook: CookType, except: Amr) =>
    amrs.some((o) => o !== except && (o.state === 'DOCKED' || (o.state === 'E_STOP' && o.hold === 'DOCKED')) && near(o.pos, PICKUPS[cook]))
  const near = (a: Pt, b: Pt) => Math.hypot(a[0] - b[0], a[1] - b[1]) < 2

  function sendHome(r: Amr) {
    go(r, homeOf(r.id), 'RETURNING')
  }

  function finishTask(r: Amr) {
    const t = taskOf(r.taskId)
    if (t && !t.finished_at) t.finished_at = iso(now)
    r.taskId = null
  }

  /* ── 손님 ── */

  function arrive() {
    const party = [1, 2, 2, 2, 3, 4][Math.floor(rand() * 6)]
    const fits = ASSIGN_ORDER.map((id) => tableOf(id)!).filter((t) => t.status === 'AVAILABLE' && t.seats >= party)
    fits.sort((a, b) => a.seats - b.seats)
    const table = fits[0]
    if (!table) return
    const visitId = `V-${pad(++seq.visit, 4)}`
    log('VISIT', visitId, null, 'ASSIGNED', 'ENTRANCE_UI', `입구 접수 ${party}명 → ${table.table_id}번`)
    table.visit = { visit_id: visitId, party_size: party, status: 'ASSIGNED', checked_in_at: iso(now), seated_at: null, ended_at: null }
    table.visit_id = visitId
    setTable(table, 'ASSIGNED', 'WORKFLOW', `${table.table_id}번 배정`)
    newTask({ task_type: 'GUIDE', state: 'GUIDE_PENDING', visit_id: visitId, table_id: table.table_id, party_size: party })
    visitPlan.set(visitId, { orderAt: null, orders: 0, endAt: null })
  }

  function placeOrder(table: AdminTable) {
    const v = table.visit!
    const kinds = [[1], [2], [1, 2], [1, 2], [2, 2]][Math.floor(rand() * 5)]
    const qty = new Map<number, number>()
    for (const k of kinds) qty.set(k, (qty.get(k) ?? 0) + 1)
    const orderId = `ORD-${pad(++seq.order, 4)}`
    const o: AdminOrder = {
      order_id: orderId,
      visit_id: v.visit_id,
      table_id: table.table_id,
      status: 'ORDERED',
      items: [...qty].map(([menu_id, q], i) => ({
        order_item_id: `${orderId}-${i + 1}`,
        menu_id,
        name: MENU[menu_id].name,
        qty: q,
        ready_at: null,
      })),
      created_at: iso(now),
      eta_at: null,
      delivery_step: null,
    }
    orders.push(o)
    log('ORDER', orderId, null, 'ORDERED', 'TABLE_UI', `${table.table_id}번 주문 ${o.items.map((i) => `${i.name} ${i.qty}`).join(', ')}`)
    for (const it of o.items) {
      const cook = MENU[it.menu_id].cook
      const arm = arms.find((a) => a.cook === cook)!
      const t = newTask({ task_type: 'COOK', state: 'COOK_TASK', order_id: orderId, table_id: table.table_id, robot_id: arm.id })
      arm.queue.push({ orderId, itemId: it.order_item_id, taskId: t.task_id, name: it.name, qty: it.qty, step: 0, stepLeft: 0 })
    }
  }

  function visitStep() {
    if (now >= nextArrival) {
      arrive()
      nextArrival = now + between(arrMin, arrMax)
    }
    for (const t of tables) {
      if (t.status === 'CLEANING' && now - (cleaningSince.get(t.table_id) ?? now) > 150_000)
        setTable(t, 'AVAILABLE', 'ADMIN_UI', `${t.table_id}번 정리 완료 — 이용 가능 (다른 관리자 화면)`)
      const v = t.visit
      if (!v || v.status !== 'IN_USE') continue
      const plan = visitPlan.get(v.visit_id)!
      const mine = orders.filter((o) => o.visit_id === v.visit_id)
      const open = mine.some((o) => o.status !== 'COMPLETED' && o.status !== 'CANCELED')
      if (plan.orderAt != null && now >= plan.orderAt) {
        placeOrder(t)
        plan.orders++
        plan.orderAt = null
      }
      if (plan.orderAt == null && !open && plan.endAt == null) {
        if (plan.orders < 2 && rand() < (plan.orders === 0 ? 1 : 0.35)) plan.orderAt = now + between(15_000, 40_000)
        else plan.endAt = now + between(40_000, 90_000)
      }
      if (plan.endAt != null && now >= plan.endAt && !open) {
        v.status = 'END_OF_USE'
        v.ended_at = iso(now)
        log('VISIT', v.visit_id, 'IN_USE', 'END_OF_USE', 'TABLE_UI', `${t.table_id}번 이용 종료`)
        setTable(t, 'CLEANING', 'WORKFLOW', `${t.table_id}번 정리 대기`)
      }
    }
  }

  /* ── 배정 ── */

  function dispatch() {
    for (const t of tasks) {
      if (t.finished_at || t.robot_id || t.task_type === 'COOK') continue
      const target = t.task_type === 'GUIDE' ? GREET : PICKUPS[t.pickupsLeft[0] ?? 'WOK']
      const free = amrs
        .filter((r) => (r.state === 'IDLE' || r.state === 'CHARGING') && !r.taskId && r.battery > 20 && r.id !== t.reassignedFrom)
        .sort((a, b) => Math.hypot(a.pos[0] - target[0], a.pos[1] - target[1]) - Math.hypot(b.pos[0] - target[0], b.pos[1] - target[1]))[0]
      if (!free) continue
      t.robot_id = free.id
      t.assigned_at = iso(now)
      free.taskId = t.task_id
      if (t.task_type === 'GUIDE') {
        setTask(t, 'GUIDE_REQ')
        go(free, GREET, 'TO_ENTRANCE')
      } else {
        setTask(t, 'SERVE_REQ')
        go(free, PICKUPS[t.pickupsLeft[0]], 'TO_PICKUP')
      }
    }
  }

  /* ── 로봇 ── */

  function amrStep(r: Amr) {
    const t = taskOf(r.taskId)
    if (r.state === 'E_STOP' || r.state === 'PAUSED') return
    if (MOVING.includes(r.state)) {
      if (now < r.waitUntil) return
      if (!move(r, STEP)) return
      r.speed = 0
      switch (r.state) {
        case 'TO_ENTRANCE':
          if (rand() < 0.12) {
            raise({
              level: 'WARN',
              source: r.id,
              code: 'W-GUIDE-02',
              message: `고객 동행 확인 지연 — ${t?.table_id}번 안내 감속·대기`,
              incident: null,
            })
            r.waitUntil = now + 5000
          }
          go(r, stopOf(t?.table_id ?? null), 'GUIDING', GUIDE_SPEED)
          return
        case 'GUIDING': {
          setAmr(r, 'ARRIVED')
          r.waitUntil = now + 3000
          const table = tableOf(t?.table_id ?? null)
          if (table?.visit) {
            table.visit.status = 'IN_USE'
            table.visit.seated_at = iso(now)
            log('VISIT', table.visit.visit_id, 'ASSIGNED', 'IN_USE', 'AMR', `${table.table_id}번 착석`)
            setTable(table, 'IN_USE', 'AMR', `${table.table_id}번 이용 중`)
            visitPlan.get(table.visit.visit_id)!.orderAt = now + between(8000, 20_000)
          }
          return
        }
        case 'TO_PICKUP': {
          const cook = t!.pickupsLeft[0]
          // 받는 곳에 다른 AMR이 있으면 조리 구역 옆 대기 칸에서 기다림
          if (dockedAt(cook, r)) go(r, WAIT_SPOT[cook], 'QUEUED')
          else {
            setAmr(r, 'DOCKED')
            r.waitUntil = now + 4000
          }
          return
        }
        case 'SERVING': {
          if (!r.retried && rand() < 0.08) {
            // 정차 위치를 한 번 놓치고 다시 붙음
            r.retried = true
            raise({ level: 'WARN', source: r.id, code: 'W-NAV-05', message: `${t!.table_id}번 서빙 위치 도착 실패 — 재시도 후 정차`, incident: null })
            r.waitUntil = now + 3000
            return
          }
          r.retried = false
          setAmr(r, 'ARRIVED')
          const o = orderOf(t!.order_id)!
          setOrder(o, 'ARRIVED', 'AMR')
          o.delivery_step = 'STOPPED'
          r.waitUntil = now + 2000
          return
        }
        case 'RETURNING':
          finishTask(r)
          setAmr(r, r.battery < 40 ? 'CHARGING' : 'IDLE')
          return
      }
    }
    if (now < r.waitUntil) return
    switch (r.state) {
      case 'QUEUED':
        if (r.path.length) {
          move(r, STEP)
          r.speed = r.path.length ? SPEED : 0
        } else if (!dockedAt(t!.pickupsLeft[0], r)) go(r, PICKUPS[t!.pickupsLeft[0]], 'TO_PICKUP')
        return
      case 'DOCKED': {
        if (errorsAt.length && now >= errorsAt[0]) {
          errorsAt.shift()
          const o = orderOf(t!.order_id)!
          r.hold = 'DOCKED'
          setAmr(r, 'E_STOP')
          setTask(t!, 'RECOVERY_WAIT')
          setOrder(o, 'ON_HOLD', 'WORKFLOW')
          raise({
            level: 'ERROR',
            source: r.id,
            code: 'E-ARM-021',
            message: '그리퍼 파지 실패 — 음식 용기를 AMR 적재 공간에 배치하지 못함',
            incident: {
              incident_id: String(seq.alarm + 1),
              source: 'DEVICE_ERROR',
              device_part: '적재 · 전달',
              task_id: t!.task_id,
              order_id: o.order_id,
              table_id: o.table_id,
              failed_state: 'DOCKED',
              failed_step: `적재 ${o.items.length + 1}/${o.items.length + 2} · 용기 파지`,
              hint: '그리퍼 주변 이물 제거 · 용기 위치 재정렬 · 장치 상태 정상',
              admin_choice: null,
              result: null,
              resolved_at: null,
            },
          })
          return
        }
        t!.pickupsLeft.shift()
        if (t!.pickupsLeft.length) go(r, PICKUPS[t!.pickupsLeft[0]], 'TO_PICKUP')
        else {
          setOrder(orderOf(t!.order_id)!, 'SERVING', 'AMR')
          go(r, stopOf(t!.table_id), 'SERVING')
        }
        return
      }
      case 'ARRIVED': {
        if (t?.task_type === 'SERVE') {
          const o = orderOf(t.order_id)!
          if (o.delivery_step === 'STOPPED') {
            o.delivery_step = 'TRANSFERRING'
            r.waitUntil = now + 3000
            return
          }
          if (o.delivery_step === 'TRANSFERRING') {
            o.delivery_step = 'DONE'
            r.waitUntil = now + 1500
            return
          }
          o.delivery_step = null
          setOrder(o, 'COMPLETED', 'TABLE_UI')
        }
        if (r.battery < 25)
          raise({ level: 'INFO', source: r.id, code: 'I-BAT-01', message: `배터리 ${Math.round(r.battery)}% — 충전대로 복귀`, incident: null })
        sendHome(r)
        return
      }
      case 'IDLE':
      case 'CHARGING':
        if (atHome(r)) {
          r.battery = Math.min(100, r.battery + 0.15)
          if (r.state === 'CHARGING' && r.battery >= 90) setAmr(r, 'IDLE')
        }
        return
    }
  }

  function armStep(a: Arm) {
    if (a.state === 'E_STOP') return
    if (!a.job) {
      const next = a.queue.shift()
      if (!next) return
      const o = orderOf(next.orderId)
      if (!o || o.status === 'CANCELED') return
      a.job = { ...next, step: 0, stepLeft: ARM_STEPS[a.cook][0][1] }
      taskOf(next.taskId)!.assigned_at = iso(now)
      if (o.status === 'ORDERED') setOrder(o, 'COOKING', 'ARM')
      setArm(a, ARM_STEPS[a.cook][0][0])
      return
    }
    const j = a.job
    j.stepLeft -= STEP
    if (j.stepLeft > 0) return
    const steps = ARM_STEPS[a.cook]
    if (++j.step < steps.length) {
      j.stepLeft = steps[j.step][1]
      setArm(a, steps[j.step][0])
      return
    }
    // 받는 곳에 내려놓음
    const o = orderOf(j.orderId)!
    const item = o.items.find((i) => i.order_item_id === j.itemId)!
    item.ready_at = iso(now)
    const ct = taskOf(j.taskId)!
    ct.finished_at = iso(now)
    a.job = null
    setArm(a, 'IDLE')
    if (o.items.every((i) => i.ready_at) && o.status === 'COOKING') {
      setOrder(o, 'READY', 'ARM')
      const cooks = [...new Set(o.items.map((i) => MENU[i.menu_id].cook))].sort() as CookType[]
      newTask({ task_type: 'SERVE', state: 'SERVE_PENDING', order_id: o.order_id, table_id: o.table_id, visit_id: o.visit_id, pickup: cooks[cooks.length - 1], pickupsLeft: cooks })
    }
  }

  function setArm(a: Arm, s: ArmState) {
    if (a.state === s) return
    log('ROBOT', a.id, a.state, s, 'ARM', `${a.id} ${a.state} → ${s}`)
    a.state = s
  }

  /* ── 관리자 조작 (WEB-08) ── */

  function check(req: OperationRequest): string | null {
    const id = req.target_id
    switch (req.kind) {
      case 'SET_TABLE_STATUS': {
        const t = tableOf(Number(id))
        const to = req.params?.status
        if (!t || !to) return '없는 테이블이에요'
        if (to === t.status) return null
        if (to === 'ASSIGNED' || to === 'IN_USE') return '손님 배정은 입구 키오스크에서만 할 수 있어요'
        if (to === 'AVAILABLE' && t.status !== 'CLEANING') return '진행 중인 손님이 있어 비울 수 없어요 (중복 배정 방지)'
        if (to === 'CLEANING' && t.status === 'ASSIGNED') return '안내 중인 손님이 있어요'
        if (to === 'CLEANING' && t.visit && orders.some((o) => o.visit_id === t.visit!.visit_id && !['COMPLETED', 'CANCELED'].includes(o.status)))
          return '아직 전달하지 않은 음식이 있어요'
        return null
      }
      case 'PAUSE': {
        const r = amrs.find((x) => x.id === id)
        if (!r) return 'AMR만 일시 중단할 수 있어요'
        if (r.state === 'E_STOP') return '비상 정지 중이에요'
        if (r.state === 'PAUSED') return '이미 일시 중단됐어요'
        return null
      }
      case 'RESUME':
        return amrs.find((x) => x.id === id)?.state === 'PAUSED' ? null : '일시 중단 상태가 아니에요'
      case 'REASSIGN': {
        const r = amrs.find((x) => x.id === id)
        if (!r?.taskId) return '맡은 임무가 없어요'
        if (r.state === 'E_STOP') return '비상 정지 중이에요 — 알람에서 먼저 처리해 주세요'
        if (r.state === 'ARRIVED') return '이미 도착해 전달 중이에요'
        return null
      }
      case 'E_STOP':
        return [...amrs, ...arms].find((x) => x.id === id)?.state === 'E_STOP' ? '이미 비상 정지 중이에요' : null
      case 'INCIDENT_RETRY':
      case 'INCIDENT_STOP': {
        const al = alarms.find((x) => x.alarm_id === id)
        if (!al?.incident) return '처리할 오류가 아니에요'
        if (al.incident.resolved_at) return '이미 처리된 오류예요'
        return null
      }
      case 'ACK_ALARM':
        return null
    }
  }

  /** 실제 적용. 실패하면 메시지 */
  function apply(req: OperationRequest): string | null {
    const late = check(req)
    if (late) return late
    const id = req.target_id
    const amr = amrs.find((x) => x.id === id)
    const arm = arms.find((x) => x.id === id)
    switch (req.kind) {
      case 'SET_TABLE_STATUS': {
        const t = tableOf(Number(id))!
        const to = req.params!.status!
        if (to === 'CLEANING' && t.visit) {
          t.visit.status = 'END_OF_USE'
          t.visit.ended_at = iso(now)
          log('VISIT', t.visit.visit_id, 'IN_USE', 'END_OF_USE', 'ADMIN_UI', `${t.table_id}번 이용 종료 (admin)`)
        }
        setTable(t, to, 'ADMIN_UI', to === 'AVAILABLE' ? `${t.table_id}번 정리 완료 — 이용 가능 (admin)` : `${t.table_id}번 정리 대기로 변경 (admin)`)
        if (to === 'AVAILABLE')
          raise({ level: 'INFO', source: 'SYSTEM', code: 'I-TBL-03', message: `${t.table_id}번 정리 완료 — 이용 가능으로 변경 (admin)`, incident: null })
        return null
      }
      case 'PAUSE':
        amr!.hold = amr!.state
        setAmr(amr!, 'PAUSED')
        return null
      case 'RESUME':
        setAmr(amr!, amr!.hold ?? 'IDLE')
        amr!.hold = null
        return null
      case 'REASSIGN': {
        const old = taskOf(amr!.taskId)!
        const free = amrs.some((r) => r !== amr && (r.state === 'IDLE' || r.state === 'CHARGING') && !r.taskId && r.battery > 20)
        if (!free) return '맡길 수 있는 AMR이 없어요'
        setTask(old, 'REASSIGN', true)
        newTask({
          task_type: old.task_type,
          state: old.task_type === 'GUIDE' ? 'GUIDE_PENDING' : 'SERVE_PENDING',
          visit_id: old.visit_id,
          order_id: old.order_id,
          table_id: old.table_id,
          party_size: old.party_size,
          pickup: old.pickup,
          pickupsLeft: old.task_type === 'SERVE' ? [...new Set(orderOf(old.order_id)!.items.map((i) => MENU[i.menu_id].cook))].sort() as CookType[] : [],
          reassignedFrom: amr!.id,
        })
        amr!.taskId = null
        amr!.hold = null
        sendHome(amr!)
        dispatch()
        return null
      }
      case 'E_STOP': {
        const dev = amr ?? arm!
        if (amr) {
          if (amr.state !== 'PAUSED') amr.hold = amr.state
          setAmr(amr, 'E_STOP')
        } else {
          arm!.hold = arm!.state
          setArm(arm!, 'E_STOP')
        }
        const t = taskOf(amr ? amr.taskId : (arm!.job?.taskId ?? null))
        if (t) setTask(t, 'RECOVERY_WAIT')
        const o = orderOf(t?.order_id ?? null)
        if (o && !['COMPLETED', 'CANCELED'].includes(o.status)) setOrder(o, 'ON_HOLD', 'ADMIN_UI')
        raise({
          level: 'ERROR',
          source: dev.id,
          code: 'E-STOP-00',
          message: '관리자 비상 정지',
          incident: {
            incident_id: String(seq.alarm + 1),
            source: 'ADMIN_STOP',
            device_part: null,
            task_id: t?.task_id ?? null,
            order_id: o?.order_id ?? null,
            table_id: t?.table_id ?? null,
            failed_state: dev.hold,
            failed_step: null,
            hint: '주변에 사람·장애물이 없는지 확인',
            admin_choice: null,
            result: null,
            resolved_at: null,
          },
        })
        return null
      }
      case 'INCIDENT_RETRY':
      case 'INCIDENT_STOP': {
        const al = alarms.find((x) => x.alarm_id === id)!
        const inc = al.incident!
        const retry = req.kind === 'INCIDENT_RETRY'
        inc.admin_choice = retry ? 'RETRY' : 'STOP'
        inc.result = retry ? 'RESUME' : 'CANCELED'
        inc.resolved_at = iso(now)
        al.acked = true
        log('INCIDENT', al.alarm_id, 'OPEN', inc.result, 'ADMIN_UI', `${al.code} ${retry ? '재시도' : '작업 취소'} (admin)`, { alarm_id: al.alarm_id })
        const t = taskOf(inc.task_id)
        const o = orderOf(inc.order_id)
        const r = amrs.find((x) => x.id === al.source)
        const ar = arms.find((x) => x.id === al.source)
        if (retry) {
          if (t && !t.finished_at) {
            setTask(t, 'RESUME')
            setTask(t, t.task_type === 'GUIDE' ? 'GUIDE_REQ' : t.task_type === 'SERVE' ? 'SERVE_REQ' : 'COOK_TASK')
          }
          if (o?.status === 'ON_HOLD') setOrder(o, orderHold.get(o.order_id) ?? 'COOKING', 'ADMIN_UI')
          if (r && r.state === 'E_STOP') {
            const back = r.hold ?? 'IDLE'
            setAmr(r, back)
            if (back === 'DOCKED') r.waitUntil = now + 4000
            r.hold = null
          }
          if (ar && ar.state === 'E_STOP') {
            setArm(ar, ar.hold ?? 'IDLE')
            ar.hold = null
          }
        } else {
          if (t && !t.finished_at) setTask(t, 'CANCELED', true)
          if (o && !['COMPLETED', 'CANCELED'].includes(o.status)) setOrder(o, 'CANCELED', 'ADMIN_UI')
          if (r) {
            r.taskId = null
            r.hold = null
            sendHome(r)
          }
          if (ar) {
            ar.job = null
            ar.hold = null
            setArm(ar, 'IDLE')
          }
        }
        return null
      }
      case 'ACK_ALARM': {
        const al = alarms.find((x) => x.alarm_id === id)
        if (al) al.acked = true
        return null
      }
    }
  }

  function request(req: OperationRequest): OperationAccepted {
    const dup = [...ops.values()].find((o) => o.req.request_key === req.request_key)
    if (dup) return { operation_id: dup.status.operation_id, result: 'ACCEPTED', reason: null }
    const operation_id = `OP-${pad(++seq.op, 4)}`
    const why = check(req)
    if (why) return { operation_id, result: 'CONFLICT', reason: why }
    const op: Op = { req, status: { operation_id, status: 'PENDING', message: null } }
    ops.set(operation_id, op)
    opQueue.push(op)
    return { operation_id, result: 'ACCEPTED', reason: null }
  }

  /* ── 진행 ── */

  function step() {
    now += STEP
    for (const op of opQueue.splice(0)) {
      const err = apply(op.req)
      op.status = { ...op.status, status: err ? 'FAILED' : 'SUCCEEDED', message: err }
    }
    visitStep()
    dispatch()
    for (const a of arms) armStep(a)
    for (const r of amrs) amrStep(r)
    if (version % 2 === 0) {
      frames.push({
        t: iso(now),
        robots: amrs.map((r) => {
          const [x, y] = toMap(r.pos)
          return { robot_id: r.id, x, y, state: r.state }
        }),
      })
      if (frames.length > 3 * 3600) frames.shift()
    }
    version++
  }

  function overview(): AdminOverview {
    const recent = now - 30 * 60_000
    return {
      server_time: iso(now),
      ros_connected: true,
      robots: [
        ...amrs.map((r) => {
          const [x, y] = toMap(r.pos)
          return {
            type: 'AMR' as const,
            robot_id: r.id,
            state: r.state,
            hold_state: r.hold,
            task_id: r.taskId,
            last_seen_at: iso(now - 100),
            pose: { x, y, yaw: r.yaw },
            battery_pct: Math.round(r.battery),
            is_charging: atHome(r) && (r.state === 'IDLE' || r.state === 'CHARGING') && r.battery < 100,
            speed: r.path.length && now >= r.waitUntil && r.state !== 'PAUSED' && r.state !== 'E_STOP' ? r.speed / 100 : 0,
            path: r.path.map(toMap),
          }
        }),
        ...arms.map((a) => {
          const steps = ARM_STEPS[a.cook]
          const j = a.job
          return {
            type: 'ARM' as const,
            robot_id: a.id,
            cook_type: a.cook,
            state: a.state,
            hold_state: a.hold,
            task_id: j?.taskId ?? null,
            last_seen_at: iso(now - 100),
            cook: j
              ? {
                  order_id: j.orderId,
                  name: j.name,
                  qty: j.qty,
                  step: j.step + 1,
                  steps: steps.length,
                  remaining_sec: Math.round((j.stepLeft + steps.slice(j.step + 1).reduce((s, x) => s + x[1], 0)) / 1000),
                }
              : null,
          }
        }),
      ],
      tables: structuredClone(tables),
      orders: structuredClone(
        orders.filter((o) => !['COMPLETED', 'CANCELED'].includes(o.status) || Date.parse(o.created_at) > recent).slice(-30),
      ),
      tasks: tasks
        .filter((t) => !t.finished_at || Date.parse(t.finished_at) > now - 60_000)
        .map((t) => {
          const c: Partial<Task> = structuredClone(t)
          delete c.pickupsLeft
          delete c.reassignedFrom
          return c as AdminTask
        }),
      alarms: structuredClone(alarms.slice(-50).reverse()),
      version,
    }
  }

  return {
    get now() {
      return now
    },
    step,
    runUntil(t: number) {
      while (now + STEP <= t) step()
    },
    overview,
    request,
    operation: (id: string) => ops.get(id)?.status ?? null,
    events: (from: number, to: number) => events.filter((e) => Date.parse(e.created_at) >= from && Date.parse(e.created_at) <= to),
    frames: (from: number, to: number) => frames.filter((f) => Date.parse(f.t) >= from && Date.parse(f.t) <= to),
  }
}

export type Sim = ReturnType<typeof createSim>

export interface AdminMockOptions {
  /** 화면을 열기 전에 미리 돌려 둘 시간(분) */
  warmupMin?: number
  /** 화면 갱신 간격(ms). 문서 기준 최대 2 Hz */
  pushMs?: number
  seed?: number
  now?: () => number
}

export function createMockAdminApi(o: AdminMockOptions = {}): AdminApi {
  const clock = o.now ?? Date.now
  const start = clock()
  const warm = (o.warmupMin ?? 25) * 60_000
  // 화면을 열기 2분쯤 전에 그리퍼 오류 하나 → A3에서 재시도·작업 취소를 해 볼 수 있음 (그 받는 곳은 처리 전까지 막힘)
  const sim = createSim({ start: start - warm, seed: o.seed, errorsAt: warm > 8 * 60_000 ? [start - 2 * 60_000] : [] })
  sim.runUntil(start)

  const subs = new Set<(ov: AdminOverview) => void>()
  let timer: ReturnType<typeof setInterval> | null = null
  const push = () => {
    sim.runUntil(clock())
    const ov = sim.overview()
    subs.forEach((cb) => cb(ov))
  }

  return {
    getOverview: async () => (sim.runUntil(clock()), sim.overview()),
    requestOperation: async (req) => sim.request(req),
    getOperation: async (id) => {
      sim.runUntil(clock())
      return sim.operation(id) ?? { operation_id: id, status: 'UNKNOWN', message: null }
    },
    subscribeOverview(cb, onConnection) {
      subs.add(cb)
      onConnection?.(true)
      cb(sim.overview())
      timer ??= setInterval(push, o.pushMs ?? 500)
      return () => {
        subs.delete(cb)
        if (!subs.size && timer) {
          clearInterval(timer)
          timer = null
        }
      }
    },
    getEvents: async ({ from, to }) => sim.events(Date.parse(from), Date.parse(to)),
    getReplay: async ({ from, to }) => sim.frames(Date.parse(from), Date.parse(to)),
  }
}
