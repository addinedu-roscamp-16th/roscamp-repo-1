import { useState } from 'react'
import type { AdminOverview, AdminTable, ArmView, CookType, TableStatus } from '../api'
import { TABLES } from '../api/storeLayout'
import { useAdmin } from './context'
import {
  C,
  COOK_NAME,
  PICKUP_NAME,
  TABLE_STATUS,
  armStateText,
  hhmm,
  itemChip,
  itemsText,
  minutesSince,
  mmss,
  orderText,
  robotName,
  stateChip,
  toneStyle,
} from './labels'
import s from './admin.module.css'

const MENU_COOK: Record<number, CookType> = { 1: 'FRY', 2: 'WOK' }

/** A2 테이블 · 주문 · 조리 */
export function TablesOrders() {
  const { ov, hasData } = useAdmin()
  const offline = !hasData
  const count = (st: TableStatus) => ov.tables.filter((t) => t.status === st).length
  const seats = ov.tables.reduce((n, t) => n + t.seats, 0)
  return (
    <div className={s.a2}>
      <main className={s.a2Main}>
        <div className={s.a2Head}>
          <h1 className={s.h1}>테이블 현황</h1>
          {offline ? (
            <div className={s.counts}>
              <span>
                · {ov.tables.length}개 테이블 {seats}석 · 상태 확인 안 됨
              </span>
            </div>
          ) : (
            <div className={s.counts}>
              <span>
                <b>이용 가능</b> {count('AVAILABLE')}
              </span>
              <span>
                <b style={{ color: C.blue }}>안내 중</b> {count('ASSIGNED')}
              </span>
              <span>
                <b style={{ color: C.green }}>이용 중</b> {count('IN_USE')}
              </span>
              <span>
                <b>정리 대기</b> {count('CLEANING')}
              </span>
              <span>
                · {ov.tables.length}개 테이블 {seats}석
              </span>
            </div>
          )}
          <div style={{ flexGrow: 1 }} />
          <span className={s.small}>상태 변경 시 중복 배정 여부를 먼저 검사합니다</span>
        </div>
        {ov.tables.length === 0 && <p className={s.muted}>테이블 정보가 없어요</p>}
        <div className={s.tableGrid}>
          {[...ov.tables]
            .sort((a, b) => a.table_id - b.table_id)
            .map((t) => (
              <TableCard key={t.table_id} t={t} ov={ov} offline={offline} />
            ))}
        </div>
        <h2 className={s.h1} style={{ fontSize: 17 }}>
          조리 구역 (로봇팔 {ov.robots.filter((r) => r.type === 'ARM').length}대 · 받는 곳)
        </h2>
        <div className={s.tableGrid}>
          {ov.robots
            .filter((r): r is ArmView => r.type === 'ARM')
            .map((a) => (
              <ArmCard key={a.robot_id} a={a} offline={offline} />
            ))}
          <PickupCard ov={ov} offline={offline} />
        </div>
      </main>
      <OrdersPanel ov={ov} />
    </div>
  )
}

function TableCard({ t, ov, offline }: { t: AdminTable; ov: AdminOverview; offline: boolean }) {
  const { run, busy, now } = useAdmin()
  const [menu, setMenu] = useState(false)
  const spec = TABLES.find((x) => x.id === t.table_id)
  const where = spec && spec.seats === 4 ? '가운데' : '벽쪽'
  const [chip, tone] = offline ? (['확인 안 됨', 'gray'] as const) : TABLE_STATUS[t.status]
  const v = t.visit
  const guide = ov.tasks.find((x) => x.task_type === 'GUIDE' && x.visit_id === v?.visit_id && !x.finished_at)
  const orders = ov.orders.filter((o) => o.visit_id === v?.visit_id)
  const latest = orders[orders.length - 1]
  const serveTask =
    latest && ov.tasks.find((x) => x.task_type === 'SERVE' && x.order_id === latest.order_id && !x.finished_at)

  let line1 = ''
  let line2 = ''
  if (offline) {
    line1 = '상태를 아직 몰라요'
    line2 = '서버에 연결되면 보여요'
  } else if (t.status === 'AVAILABLE') {
    line1 = '빈 자리'
    line2 = '다음 손님 배정 가능'
  } else if (t.status === 'ASSIGNED' && v) {
    line1 = `${v.party_size}명 · ${guide?.robot_id ? `${robotName(guide.robot_id)} 안내 중` : '안내 AMR 기다리는 중'}`
    line2 = `${hhmm(v.checked_in_at)} 입구 접수`
  } else if (t.status === 'IN_USE' && v) {
    line1 = `${v.party_size}명 · 이용 ${minutesSince(v.seated_at ?? v.checked_in_at, now)}분`
    line2 = latest
      ? `${latest.order_id} ${itemsText(latest)} · ${orderText(latest)}${serveTask?.robot_id ? ` (${robotName(serveTask.robot_id)} 배정)` : ''}`
      : '아직 주문 없음'
  } else if (t.status === 'CLEANING') {
    line1 = `${hhmm(v?.ended_at ?? null)} 이용 종료 입력`
    line2 = '신규 배정 대상에서 제외됨'
  }

  const set = (status: TableStatus) => ({
    kind: 'SET_TABLE_STATUS' as const,
    target_id: String(t.table_id),
    params: { status },
  })
  const cleaning = !offline && t.status === 'CLEANING'

  return (
    <div
      className={s.card}
      style={cleaning ? { border: `1px dashed ${C.muted}` } : undefined}
      aria-label={`${t.table_id}번 테이블`}
    >
      <div className={s.cardHead}>
        <b className={s.cardNo}>{t.table_id}번</b>
        <span className={s.small} style={{ fontSize: 13 }}>
          {t.seats}인석 · {where}
        </span>
        <span className={s.chip} style={{ ...toneStyle(tone), marginLeft: 'auto' }}>
          {chip}
        </span>
      </div>
      <div className={s.cardLines}>
        <span>{line1}</span>
        <span className={s.muted}>{line2}</span>
      </div>
      {cleaning ? (
        <button
          className={s.primaryBtn}
          disabled={busy(set('AVAILABLE'))}
          onClick={() => void run(set('AVAILABLE'), `${t.table_id}번 이용 가능으로 바꿨어요`)}
        >
          정리 완료 → 이용 가능
        </button>
      ) : (
        <div style={{ position: 'relative' }}>
          <button
            className={s.outBtn}
            style={{ width: '100%' }}
            aria-expanded={menu}
            disabled={offline}
            onClick={() => setMenu(!menu)}
          >
            상태 변경
          </button>
          {menu && (
            <div role="menu" className={s.menu}>
              {(['CLEANING', 'AVAILABLE'] as TableStatus[]).map((st) => (
                <button
                  key={st}
                  role="menuitem"
                  disabled={st === t.status || busy(set(st))}
                  onClick={() => {
                    setMenu(false)
                    void run(set(st), `${t.table_id}번 ${TABLE_STATUS[st][0]}(으)로 바꿨어요`)
                  }}
                >
                  {st === 'CLEANING' ? '정리 대기로 (이용 종료 처리)' : '이용 가능으로'}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ArmCard({ a, offline }: { a: ArmView; offline: boolean }) {
  const [chip, tone] = stateChip(a, offline)
  const c = a.cook
  const pct = c ? Math.round(((c.step - 1) / c.steps) * 100 + 100 / c.steps / 2) : 0
  return (
    <div className={s.card} aria-label={`${COOK_NAME[a.cook_type]} 로봇팔`}>
      <div className={s.cardHead}>
        <b style={{ fontSize: 16 }}>{COOK_NAME[a.cook_type]} 로봇팔</b>
        <span className={s.small}>{robotName(a.robot_id)}</span>
        <span className={s.chip} style={{ ...toneStyle(tone), marginLeft: 'auto' }}>
          {chip}
        </span>
      </div>
      <span className={s.cardText}>
        {c
          ? `${c.order_id} ${c.name} ${c.qty}`
          : offline
            ? '서버 연결을 기다리는 중'
            : a.state === 'E_STOP'
              ? '비상 정지 · 복구 대기'
              : '받은 주문 없음'}
      </span>
      <div className={s.track} style={{ height: 6 }}>
        <span
          style={{
            width: `${pct}%`,
            background: a.state === 'E_STOP' ? C.red : '#3DD68C',
          }}
        />
      </div>
      <span className={s.small}>
        {c ? `${c.step}/${c.steps} ${armStateText(a.state)} (남은 ${mmss(c.remaining_sec)})` : '—'}
      </span>
    </div>
  )
}

/** 받는 곳: 조리가 끝나 AMR이 가져가기를 기다리는 음식 */
function PickupCard({ ov, offline }: { ov: AdminOverview; offline: boolean }) {
  const { now } = useAdmin()
  const waiting = ov.orders
    .filter((o) => o.status === 'READY' || o.status === 'ON_HOLD' || o.status === 'COOKING')
    .flatMap((o) => o.items.filter((i) => i.ready_at).map((i) => ({ o, i })))
  const first = waiting[0]
  const task =
    first && ov.tasks.find((t) => t.task_type === 'SERVE' && t.order_id === first.o.order_id && !t.finished_at)
  return (
    <div className={s.card} aria-label="받는 곳">
      <div className={s.cardHead}>
        <b style={{ fontSize: 16 }}>받는 곳</b>
        <span className={s.small}>튀김 · 볶음밥</span>
        <span
          className={s.chip}
          style={{
            ...toneStyle(waiting.length ? 'amber' : 'gray'),
            marginLeft: 'auto',
          }}
        >
          {offline ? '확인 안 됨' : waiting.length ? `음식 대기 ${waiting.length}` : '비어 있음'}
        </span>
      </div>
      <span className={s.cardText}>
        {first
          ? `${PICKUP_NAME[MENU_COOK[first.i.menu_id] ?? 'WOK']} · ${first.o.order_id} ${first.i.name} ${first.i.qty}`
          : offline ? '서버 연결을 기다리는 중' : '가져갈 음식 없음'}
      </span>
      <div className={s.track} style={{ height: 6 }}>
        <span style={{ width: first ? '100%' : '0%', background: '#F5B942' }} />
      </div>
      <span className={s.small}>
        {first
          ? `${task?.robot_id ? `픽업 예정 ${robotName(task.robot_id)}` : '픽업 AMR 배정 대기'} · ${mmss((now - Date.parse(first.i.ready_at!)) / 1000)} 경과`
          : '—'}
      </span>
    </div>
  )
}

function OrdersPanel({ ov }: { ov: AdminOverview }) {
  const [done, setDone] = useState(false)
  const list = ov.orders
    .filter((o) =>
      done ? o.status === 'COMPLETED' || o.status === 'CANCELED' : o.status !== 'COMPLETED' && o.status !== 'CANCELED',
    )
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
  return (
    <aside aria-label="주문 · 조리 현황" className={s.orders}>
      <div className={s.rowBetween}>
        <h2 className={s.h1}>주문 · 조리 현황</h2>
        <div className={s.toggle2}>
          <button className={!done ? s.toggleOn : s.toggleOff} aria-pressed={!done} onClick={() => setDone(false)}>
            진행 중
          </button>
          <button className={done ? s.toggleOn : s.toggleOff} aria-pressed={done} onClick={() => setDone(true)}>
            완료
          </button>
        </div>
      </div>
      <div className={s.flow} aria-label="주문 단계">
        {['접수', '조리', '서빙 준비', '서빙', '완료'].map((x, i) => (
          <span key={x}>
            {i > 0 && <span className={s.arrow}>→</span>}
            <span className={s.flowChip}>{x}</span>
          </span>
        ))}
      </div>
      <ul className={s.orderList}>
        {list.length === 0 && (
          <li className={s.muted}>{done ? '최근 30분 동안 끝난 주문이 없어요' : '진행 중인 주문이 없어요'}</li>
        )}
        {list.map((o) => (
          <li key={o.order_id} className={s.orderCard}>
            <div className={s.cardHead}>
              <b style={{ fontSize: 16 }}>{o.order_id}</b>
              <span className={s.small} style={{ fontSize: 13 }}>
                {o.table_id}번
              </span>
              <span className={s.small} style={{ marginLeft: 'auto' }}>
                {hhmm(o.created_at)}
              </span>
            </div>
            {o.items.map((i) => {
              const [chip, tone] = itemChip(o, !!i.ready_at)
              return (
                <div key={i.order_item_id} className={s.orderItem}>
                  <span>
                    {i.name} × {i.qty}
                  </span>
                  <span className={s.chip} style={toneStyle(tone)}>
                    {chip}
                  </span>
                </div>
              )
            })}
          </li>
        ))}
      </ul>
    </aside>
  )
}
