import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { AdminOverview, AdminTask, AmrView, ArmView, RobotView } from '../api'
import { fromMap, type Pt } from '../api/storeLayout'
import { useAdmin } from './context'
import {
  ARM_STEPS,
  C,
  LEVEL,
  ROUTE,
  amrDoing,
  amrKind,
  amrTarget,
  armStateText,
  armTitle,
  hhmm,
  itemsText,
  mmss,
  robotName,
  stateChip,
  taskNo,
  taskSteps,
  toneStyle,
  type RouteKind,
} from './labels'
import s from './admin.module.css'
import { StoreMap3D, type MapArm, type MapBot, type MapRoute } from './StoreMap3D'

const isAmr = (r: RobotView): r is AmrView => r.type === 'AMR'
const isArm = (r: RobotView): r is ArmView => r.type === 'ARM'
const taskOf = (ov: AdminOverview, id: string | null) => (id ? (ov.tasks.find((t) => t.task_id === id) ?? null) : null)

const FILTERS: { key: RouteKind | 'all'; label: string; color: string }[] = [
  { key: 'all', label: '전체', color: C.muted },
  { key: 'pick', label: '픽업', color: ROUTE.pick },
  { key: 'serve', label: '서빙', color: ROUTE.serve },
  { key: 'guide', label: '안내', color: ROUTE.guide },
  { key: 'back', label: '복귀', color: ROUTE.back },
]
const KIND_SHORT: Record<RouteKind, string> = { pick: '픽업', serve: '서빙', guide: '안내', back: '복귀', idle: '대기', error: '정지' }

/** A1 통합 관제 */
export function Monitoring() {
  const { ov, now } = useAdmin()
  const amrs = ov.robots.filter(isAmr)
  const arms = ov.robots.filter(isArm)
  const [tab, setTab] = useState<'AMR' | 'ARM'>('AMR')
  const [picked, setSelected] = useState<string>('')
  // 고른 게 없으면 일하는 AMR → 첫 AMR (서버 현황이 늦게 와도 자동으로 골라짐)
  const selected = picked || (amrs.find((r) => r.task_id)?.robot_id ?? amrs[0]?.robot_id ?? '')
  const [view, setView] = useState<'3d' | 'top'>('3d')
  const [filter, setFilter] = useState<RouteKind | 'all'>('all')
  const [frozen, setFrozen] = useState<AdminOverview | null>(null)
  const shown = frozen ?? ov

  const list = tab === 'AMR' ? amrs : arms
  const sel = ov.robots.find((r) => r.robot_id === selected) ?? null

  const bots: MapBot[] = shown.robots.filter(isAmr).map((r) => {
    const kind = amrKind(r, taskOf(shown, r.task_id))
    return {
      id: r.robot_id,
      pos: fromMap(r.pose.x, r.pose.y),
      color: ROUTE[kind],
      label: r.robot_id.replace(/\D/g, ''),
      sub: r.state === 'PAUSED' ? '중단' : KIND_SHORT[kind],
      selected: r.robot_id === selected,
      dashed: r.state === 'PAUSED',
    }
  })
  const routes: MapRoute[] = shown.robots.filter(isAmr).flatMap((r) => {
    if (!r.path.length) return []
    const kind = amrKind(r, taskOf(shown, r.task_id))
    const pts: Pt[] = [fromMap(r.pose.x, r.pose.y), ...r.path.map(([x, y]) => fromMap(x, y))]
    return [{ pts, color: ROUTE[kind], dim: filter !== 'all' && filter !== kind }]
  })
  const mapArms: MapArm[] = shown.robots.filter(isArm).map((a) => {
    const color = a.state === 'E_STOP' ? ROUTE.error : a.cook ? '#22C55E' : '#9CA3AF'
    const c = a.cook
    return {
      cook: a.cook_type,
      title: armTitle(a),
      chip: stateChip(a)[0],
      color,
      state: c ? armStateText(a.state) : stateChip(a)[0],
      order: c ? `${c.order_id} · ${c.name} ${c.qty}` : '조리 대기',
      step: c ? `${c.step}/${c.steps} ${armStateText(a.state)} · 남은 ${mmss(c.remaining_sec)}` : '받은 주문 없음',
      pct: c ? Math.round(((c.step - 1) / c.steps) * 100 + 100 / c.steps / 2) : 0,
    }
  })

  return (
    <div className={s.a1}>
      <SummaryBar ov={ov} now={now} />
      <div className={s.a1Grid}>
        <aside aria-label="대상 목록" className={s.side}>
          <div className={s.sideHead}>
            <div className={s.rowBetween}>
              <h2 className={s.h2}>대상 목록</h2>
              <span className={s.small}>
                수신 {ov.robots.filter((r) => now - Date.parse(r.last_seen_at) < 3000).length} / {ov.robots.length}
              </span>
            </div>
            <div className={s.seg2} role="tablist">
              {(['AMR', 'ARM'] as const).map((k) => (
                <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? s.segOn : s.segOff} onClick={() => setTab(k)}>
                  {k === 'AMR' ? `AMR ${amrs.length}` : `로봇팔 ${arms.length}`}
                </button>
              ))}
            </div>
          </div>
          <ul className={s.targetList}>
            {list.length === 0 && <li className={s.emptyRow}>{tab === 'AMR' ? 'AMR 정보가 없어요' : '로봇팔 정보가 없어요'}</li>}
            {list.map((r) => (
              <TargetRow key={r.robot_id} r={r} ov={ov} on={r.robot_id === selected} onPick={() => setSelected(r.robot_id)} />
            ))}
          </ul>
          <p className={s.sideFoot}>
            목록에서 고르면 지도에서 강조 · 오른쪽에 상세 표시
            <br />
            지도에서 로봇을 눌러도 골라져요
          </p>
        </aside>

        <main className={s.center}>
          <div className={s.mapBar}>
            <span className={s.muted}>지도</span>
            <b>맵 구성도 · 200×100 cm</b>
            <div role="group" aria-label="보기 방식" className={s.viewSeg}>
              <button className={view === 'top' ? s.viewOn : s.viewOff} aria-pressed={view === 'top'} onClick={() => setView('top')}>
                탑뷰
              </button>
              <button className={view === '3d' ? s.viewOn : s.viewOff} aria-pressed={view === '3d'} onClick={() => setView('3d')}>
                3D
              </button>
            </div>
            <button
              className={s.ghostBtn}
              aria-label={frozen ? '지도 다시 움직이기' : '지도 화면 멈추기'}
              onClick={() => setFrozen(frozen ? null : ov)}
            >
              {frozen ? '▶ 재생' : '❚❚ 일시정지'}
            </button>
            <div style={{ flexGrow: 1 }} />
            {FILTERS.map((f) => (
              <button
                key={f.key}
                className={`${s.chipBtn} ${filter === f.key ? s.chipOn : ''}`}
                aria-pressed={filter === f.key}
                onClick={() => setFilter(f.key)}
              >
                <span className={s.dot} style={{ background: f.color }} />
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ position: 'relative' }}>
            <StoreMap3D
              view={view}
              width={872}
              height={548}
              bots={bots}
              routes={routes}
              arms={mapArms}
              onSelect={(id) => {
                setSelected(id)
                setTab('AMR')
              }}
              label="매장 지도: AMR 위치와 남은 경로"
            />
            {bots.length > 0 && (
            <div className={s.legend}>
              {bots.map((b) => (
                <span key={b.id}>
                  <span className={s.dot} style={{ background: b.color }} /> {robotName(b.id)} {b.sub}
                </span>
              ))}
            </div>
            )}
          </div>
          <TaskQueue ov={ov} now={now} />
        </main>

        <aside aria-label="상세" className={s.detail}>
          {sel ? isAmr(sel) ? <AmrDetail r={sel} ov={ov} now={now} /> : <ArmDetail a={sel} /> : <p className={s.muted}>{ov.robots.length ? '대상을 골라 주세요' : '표시할 로봇이 없어요'}</p>}
          <RecentAlarms ov={ov} />
        </aside>
      </div>
    </div>
  )
}

/* ── 위 요약 줄 ── */

function SummaryBar({ ov, now }: { ov: AdminOverview; now: number }) {
  const amrs = ov.robots.filter(isAmr)
  const arms = ov.robots.filter(isArm)
  const late = (r: RobotView) => now - Date.parse(r.last_seen_at) > 3000
  const n = (f: (r: AmrView) => boolean) => amrs.filter(f).length
  const guide = n((r) => ['TO_ENTRANCE', 'GUIDING'].includes(r.state) || (r.state === 'ARRIVED' && taskOf(ov, r.task_id)?.task_type === 'GUIDE'))
  const serve = n((r) => ['TO_PICKUP', 'QUEUED', 'DOCKED', 'SERVING'].includes(r.state) || (r.state === 'ARRIVED' && taskOf(ov, r.task_id)?.task_type === 'SERVE'))
  const err = n((r) => r.state === 'E_STOP')
  const charging = n((r) => r.state === 'CHARGING')
  const idle = amrs.length - guide - serve - err - charging
  const used = ov.tables.filter((t) => t.status === 'IN_USE' || t.status === 'ASSIGNED').length
  const waiting = ov.tasks.filter((t) => !t.finished_at && !t.robot_id && t.task_type !== 'COOK').length
  return (
    <div className={s.summary}>
      <div className={s.sumGroup}>
        <b>AMR {amrs.length}대</b>
        <span style={{ color: C.blue }}>● 안내 {guide}</span>
        <span style={{ color: C.green }}>● 서빙 {serve}</span>
        <span style={{ color: C.sub }}>● 대기 {idle}</span>
        <span style={{ color: C.muted }}>● 충전 {charging}</span>
        <span style={{ color: err ? C.red : C.muted }}>● 오류 {err}</span>
        <span style={{ color: C.muted }}>● 수신 지연 {amrs.filter(late).length}</span>
      </div>
      <div className={s.vline} />
      <div className={s.sumGroup}>
        <b>로봇팔 {arms.length}대</b>
        <span style={{ color: C.green }}>● 조리 {arms.filter((a) => a.cook && a.state !== 'E_STOP').length}</span>
        <span style={{ color: C.muted }}>● 대기 {arms.filter((a) => !a.cook && a.state !== 'E_STOP').length}</span>
        {arms.some((a) => a.state === 'E_STOP') && <span style={{ color: C.red }}>● 오류 {arms.filter((a) => a.state === 'E_STOP').length}</span>}
      </div>
      <div className={s.vline} />
      <div className={s.sumGroup}>
        <b>
          테이블 {used}/{ov.tables.length} 이용
        </b>
        <span style={{ color: C.blue }}>안내 중 {ov.tables.filter((t) => t.status === 'ASSIGNED').length}</span>
        <span style={{ color: C.muted }}>정리 대기 {ov.tables.filter((t) => t.status === 'CLEANING').length}</span>
        <span style={{ color: C.muted }}>대기 임무 {waiting}</span>
      </div>
    </div>
  )
}

/* ── 대상 목록 한 줄 ── */

function TargetRow({ r, ov, on, onPick }: { r: RobotView; ov: AdminOverview; on: boolean; onPick: () => void }) {
  const [chip, tone] = stateChip(r)
  const task = taskOf(ov, r.task_id)
  const amr = isAmr(r)
  const pct = amr ? r.battery_pct : r.cook ? Math.round((r.cook.step / r.cook.steps) * 100) : 0
  const bad = r.state === 'E_STOP'
  const bar = bad ? C.red : amr && r.battery_pct < 25 ? C.amber : '#5BE3A0'
  return (
    <li>
      <button className={`${s.target} ${on ? s.targetOn : ''}`} style={on ? { boxShadow: `${bad ? C.red : '#3DD68C'} 3px 0 0 inset` } : undefined} onClick={onPick} aria-current={on || undefined}>
        <span className={s.targetTop}>
          <span className={s.dot} style={{ background: bad ? C.red : '#5BE3A0' }} aria-hidden="true" />
          <b>{amr ? robotName(r.robot_id) : `${armTitle(r)} · ${robotName(r.robot_id)}`}</b>
          <span className={s.chip} style={toneStyle(tone)}>
            {chip}
          </span>
        </span>
        <span className={s.targetBar}>
          <span className={s.track}>
            <span style={{ width: `${pct}%`, background: bar }} />
          </span>
          <span>{amr ? `${pct}%` : r.cook ? `${r.cook.step}/${r.cook.steps}` : '—'}</span>
        </span>
        <span className={s.targetSub}>
          {amr ? amrDoing(r, task, ov) : r.cook ? `${r.cook.order_id} ${r.cook.name} ${r.cook.qty} · ${armStateText(r.state)}` : r.state === 'E_STOP' ? '비상 정지 · 복구 대기' : '받은 주문 없음'}
        </span>
      </button>
    </li>
  )
}

/* ── 임무 큐 ── */

function TaskQueue({ ov, now }: { ov: AdminOverview; now: number }) {
  const rows = ov.tasks
    .filter((t) => t.task_type !== 'COOK' && !t.finished_at)
    .sort((a, b) => Number(a.task_id) - Number(b.task_id))
  const running = rows.filter((t) => t.robot_id).length
  const waiting = rows.length - running
  const stopped = rows.filter((t) => t.state === 'RECOVERY_WAIT').length
  return (
    <section aria-label="임무 큐" className={s.queue}>
      <div className={s.queueHead}>
        <h2 className={s.h2}>임무 큐</h2>
        <span className={s.small}>
          수행 {running - stopped} · 대기 {waiting}
          {stopped ? ` · 복구 대기 ${stopped}` : ''}
        </span>
        {stopped > 0 && (
          <Link to="/admin/alarms" className={s.queueNote}>
            오류로 멈춘 임무가 있어요 → 알람에서 처리
          </Link>
        )}
      </div>
      <div className={s.queueScroll}>
        <table className={s.qTable}>
          <thead>
            <tr>
              <th>임무</th>
              <th>유형</th>
              <th>대상</th>
              <th>배정</th>
              <th>상태</th>
              <th>대기</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className={s.muted}>
                  진행 중인 임무가 없어요
                </td>
              </tr>
            )}
            {rows.map((t) => {
              const [text, color] = queueState(t, ov)
              const o = ov.orders.find((x) => x.order_id === t.order_id)
              return (
                <tr key={t.task_id}>
                  <td>{taskNo(t.task_id)}</td>
                  <td>{t.task_type === 'GUIDE' ? '안내' : '서빙'}</td>
                  <td>{t.task_type === 'GUIDE' ? `${t.table_id}번 · ${t.party_size}명` : `${t.table_id}번 · ${o ? `${o.order_id} ${itemsText(o)}` : t.order_id}`}</td>
                  <td>{t.robot_id ? robotName(t.robot_id) : '—'}</td>
                  <td style={{ color }}>{text}</td>
                  <td>{t.robot_id ? '—' : mmss((now - Date.parse(t.created_at)) / 1000)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function queueState(t: AdminTask, ov: AdminOverview): [string, string] {
  if (t.state === 'RECOVERY_WAIT') return ['복구 대기', C.red]
  if (!t.robot_id) return ['대기 · 가용 AMR 없음', C.amber]
  const r = ov.robots.find((x) => x.robot_id === t.robot_id)
  if (r?.state === 'PAUSED') return ['일시 중단', C.amber]
  if (r?.state === 'QUEUED') return ['받는 곳 대기', C.amber]
  return ['수행 중', C.green]
}

/* ── 오른쪽 상세 ── */

function AmrDetail({ r, ov, now }: { r: AmrView; ov: AdminOverview; now: number }) {
  const { run, busy } = useAdmin()
  const [confirm, setConfirm] = useState(false)
  const task = taskOf(ov, r.task_id)
  const order = ov.orders.find((o) => o.order_id === task?.order_id) ?? null
  const [chip, tone] = stateChip(r)
  const n = r.robot_id.replace(/\D/g, '')
  const kind = amrKind(r, task)
  const steps = task ? taskSteps(task, r, order) : []
  const incident = ov.alarms.find((a) => a.source === r.robot_id && a.incident && !a.incident.resolved_at)
  const paused = r.state === 'PAUSED'
  const req = (kind: 'PAUSE' | 'RESUME' | 'REASSIGN' | 'E_STOP') => ({ kind, target_id: r.robot_id })
  const deg = Math.round((((r.pose.yaw * 180) / Math.PI) % 360 + 360) % 360)

  return (
    <div className={s.detailBody}>
      <div className={s.detailHead}>
        <span className={s.bigNo} style={{ background: ROUTE[kind] }}>
          {n}
        </span>
        <div>
          <h2 className={s.detailTitle}>{robotName(r.robot_id)}</h2>
          <span className={s.small}>
            PinkyPro · 수신 {Math.max(0.1, (now - Date.parse(r.last_seen_at)) / 1000).toFixed(1)}초 전
          </span>
        </div>
        <span className={s.chip} style={{ ...toneStyle(tone), marginLeft: 'auto' }}>
          {chip}
        </span>
      </div>
      <div className={s.tiles}>
        <Tile k="목적지" v={amrTarget(r, task)} />
        <Tile k="주문" v={task?.task_type === 'SERVE' ? (task.order_id ?? '—') : task ? `${task.party_size}명 안내` : '—'} />
        <Tile k="위치 x · y · θ" v={`${r.pose.x.toFixed(2)} · ${r.pose.y.toFixed(2)} · ${deg}°`} />
        <Tile k="속도 · 배터리" v={`${r.speed.toFixed(2)} m/s · ${r.battery_pct}%`} />
      </div>
      <h3 className={s.h3}>임무 단계{task ? ` · ${taskNo(task.task_id)}` : ''}</h3>
      {steps.length ? (
        <ol className={s.steps}>
          {steps.map((st) => (
            <li key={st.label} className={st.status === 'todo' ? s.stepTodo : undefined} aria-current={st.status === 'now' ? 'step' : undefined}>
              <span className={st.status === 'now' ? s.stepDotNow : st.status === 'done' ? s.stepDotDone : s.stepDot} />
              <span className={st.status === 'now' ? s.stepNow : undefined}>{st.label}</span>
              <span className={s.stepAt}>{st.status === 'now' ? (r.state === 'E_STOP' ? '정지' : paused ? '중단' : '진행 중') : st.at ? hhmm(st.at) : ''}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className={s.muted}>맡은 임무가 없어요</p>
      )}

      {r.state === 'E_STOP' ? (
        <div className={s.estopBox}>
          <b>비상 정지 중</b>
          <span>{incident ? `${incident.code} ${incident.message}` : '복구 대기'}</span>
          <Link to={`/admin/alarms?alarm=${incident?.alarm_id ?? ''}`} className={s.primaryBtn}>
            알람에서 재시도 · 작업 취소
          </Link>
        </div>
      ) : (
        <>
          <div className={s.btnRow}>
            <button
              className={s.outBtn}
              disabled={busy(req(paused ? 'RESUME' : 'PAUSE'))}
              onClick={() => void run(req(paused ? 'RESUME' : 'PAUSE'), paused ? `${robotName(r.robot_id)} 다시 진행해요` : `${robotName(r.robot_id)} 일시 중단했어요`)}
            >
              {paused ? '다시 진행' : '일시 중단'}
            </button>
            <button
              className={s.outBtn}
              disabled={!task || r.state === 'ARRIVED' || busy(req('REASSIGN'))}
              onClick={() => void run(req('REASSIGN'), `${task ? taskNo(task.task_id) : ''} 다른 AMR에 다시 맡겼어요`)}
            >
              재할당
            </button>
          </div>
          <button className={s.dangerBtn} onClick={() => setConfirm(true)} disabled={busy(req('E_STOP'))}>
            비상 정지
          </button>
        </>
      )}
      {confirm && (
        <ConfirmEStop
          name={robotName(r.robot_id)}
          onClose={() => setConfirm(false)}
          onYes={() => {
            setConfirm(false)
            void run(req('E_STOP'), `${robotName(r.robot_id)} 비상 정지했어요`)
          }}
        />
      )}
    </div>
  )
}

function ArmDetail({ a }: { a: ArmView }) {
  const { run, busy } = useAdmin()
  const [confirm, setConfirm] = useState(false)
  const [chip, tone] = stateChip(a)
  const c = a.cook
  const steps = ARM_STEPS[a.cook_type]
  const cur = steps.indexOf(a.state === 'E_STOP' ? ((a.hold_state as ArmView['state']) ?? 'IDLE') : a.state)
  const req = { kind: 'E_STOP' as const, target_id: a.robot_id }
  return (
    <div className={s.detailBody}>
      <div className={s.detailHead}>
        <span className={s.bigNo} style={{ background: a.state === 'E_STOP' ? ROUTE.error : '#22C55E' }}>
          {a.cook_type === 'FRY' ? '튀' : '웍'}
        </span>
        <div>
          <h2 className={s.detailTitle}>{armTitle(a)}</h2>
          <span className={s.small}>{robotName(a.robot_id)} · {a.robot_id}</span>
        </div>
        <span className={s.chip} style={{ ...toneStyle(tone), marginLeft: 'auto' }}>
          {chip}
        </span>
      </div>
      <div className={s.tiles}>
        <Tile k="주문" v={c?.order_id ?? '—'} />
        <Tile k="메뉴" v={c ? `${c.name} ${c.qty}` : '—'} />
        <Tile k="단계" v={c ? `${c.step}/${c.steps}` : '—'} />
        <Tile k="남은 시간" v={c ? mmss(c.remaining_sec) : '—'} />
      </div>
      <h3 className={s.h3}>조리 단계</h3>
      <ol className={s.steps}>
        {steps.map((st, i) => {
          const status = !c || cur < 0 ? 'todo' : i < cur ? 'done' : i === cur ? 'now' : 'todo'
          return (
            <li key={st} className={status === 'todo' ? s.stepTodo : undefined} aria-current={status === 'now' ? 'step' : undefined}>
              <span className={status === 'now' ? s.stepDotNow : status === 'done' ? s.stepDotDone : s.stepDot} />
              <span className={status === 'now' ? s.stepNow : undefined}>{armStateText(st)}</span>
              <span className={s.stepAt}>{status === 'now' ? (a.state === 'E_STOP' ? '정지' : '진행 중') : ''}</span>
            </li>
          )
        })}
      </ol>
      {a.state === 'E_STOP' ? (
        <div className={s.estopBox}>
          <b>비상 정지 중</b>
          <Link to="/admin/alarms" className={s.primaryBtn}>
            알람에서 재시도 · 작업 취소
          </Link>
        </div>
      ) : (
        <button className={s.dangerBtn} onClick={() => setConfirm(true)} disabled={busy(req)}>
          비상 정지
        </button>
      )}
      {confirm && (
        <ConfirmEStop
          name={armTitle(a)}
          onClose={() => setConfirm(false)}
          onYes={() => {
            setConfirm(false)
            void run(req, `${armTitle(a)} 비상 정지했어요`)
          }}
        />
      )}
    </div>
  )
}

function Tile({ k, v }: { k: string; v: string }) {
  return (
    <div className={s.tile}>
      <span>{k}</span>
      <b>{v}</b>
    </div>
  )
}

function ConfirmEStop({ name, onYes, onClose }: { name: string; onYes: () => void; onClose: () => void }) {
  return (
    <div className={s.dim} onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={`${name} 비상 정지`} className={s.dialog} onClick={(e) => e.stopPropagation()}>
        <h2>{name}을(를) 비상 정지할까요?</h2>
        <p>지금 하던 일을 멈추고, 알람·이력 화면에서 재시도하거나 작업을 취소할 때까지 움직이지 않아요.</p>
        <div className={s.btnRow}>
          <button className={s.outBtn} onClick={onClose} autoFocus>
            취소
          </button>
          <button className={s.dangerBtn} style={{ marginTop: 0 }} onClick={onYes}>
            비상 정지
          </button>
        </div>
      </div>
    </div>
  )
}

function RecentAlarms({ ov }: { ov: AdminOverview }) {
  const list = ov.alarms.slice(0, 2)
  return (
    <section aria-label="최근 알람" className={s.recent}>
      <div className={s.rowBetween}>
        <h3 className={s.h3} style={{ margin: 0 }}>
          최근 알람
        </h3>
        <Link to="/admin/alarms" className={s.link}>
          전체 보기
        </Link>
      </div>
      {list.length === 0 && <p className={s.muted}>알람이 없어요</p>}
      {list.map((a) => (
        <Link key={a.alarm_id} to={`/admin/alarms?alarm=${a.alarm_id}`} className={s.recentItem} style={a.level === 'ERROR' ? { background: '#3B1512' } : undefined}>
          <b style={{ color: toneStyle(LEVEL[a.level][1]).color }}>
            {LEVEL[a.level][0]} · {robotName(a.source)}
          </b>{' '}
          {hhmm(a.occurred_at)} {a.message}
        </Link>
      ))}
    </section>
  )
}
