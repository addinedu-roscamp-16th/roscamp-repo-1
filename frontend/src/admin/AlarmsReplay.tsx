import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { newRequestKey, type Alarm, type AdminOverview, type EventLogRow, type ReplayFrame } from '../api'
import { fromMap, type Pt } from '../api/storeLayout'
import { useAdmin } from './context'
import {
  C,
  CATEGORY,
  LEVEL,
  ROUTE,
  eventCategory,
  hhmm,
  hhmmss,
  robotName,
  stateWord,
  TASK_TYPE,
  taskNo,
  toneStyle,
  type EventCategory,
} from './labels'
import s from './admin.module.css'
import { StoreMap3D, type MapBot, type MapRoute } from './StoreMap3D'

type LevelFilter = 'ALL' | Alarm['level']
const PERIODS = [
  { label: '최근 10분', min: 10 },
  { label: '최근 30분', min: 30 },
  { label: '최근 1시간', min: 60 },
]
const RESULTS = { ALL: '전체', OK: '정상', BAD: '오류·취소' } as const
type ResultFilter = keyof typeof RESULTS
const TRAIL_MS = 30_000

const isBad = (e: EventLogRow) => e.entity === 'INCIDENT' || e.to_state === 'CANCELED' || e.to_state === 'E_STOP' || e.to_state === 'ON_HOLD'

/** A3 알람 · 이력 (Replay) */
export function AlarmsReplay() {
  const { ov: maybe, api, now } = useAdmin()
  const ov = maybe!
  const [params, setParams] = useSearchParams()
  const [level, setLevel] = useState<LevelFilter>('ALL')
  const alarms = ov.alarms.filter((a) => level === 'ALL' || a.level === level)
  const openFirst = ov.alarms.find((a) => a.incident && !a.incident.resolved_at)
  const selId = params.get('alarm') || openFirst?.alarm_id || ov.alarms[0]?.alarm_id || null
  const sel = ov.alarms.find((a) => a.alarm_id === selId) ?? null

  // 기간·필터
  const [period, setPeriod] = useState(1)
  const [cat, setCat] = useState<EventCategory | 'ALL'>('ALL')
  const [result, setResult] = useState<ResultFilter>('ALL')
  const [range, setRange] = useState<{ from: number; to: number } | null>(null)
  const [events, setEvents] = useState<EventLogRow[]>([])
  const [frames, setFrames] = useState<ReplayFrame[]>([])
  const [loading, setLoading] = useState(false)
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)

  const load = useCallback(
    async (from: number, to: number, at?: number) => {
      setLoading(true)
      setPlaying(false)
      try {
        const q = { from: new Date(from).toISOString(), to: new Date(to).toISOString() }
        const [ev, fr] = await Promise.all([api.getEvents(q), api.getReplay(q)])
        setRange({ from, to })
        setEvents(ev)
        setFrames(fr)
        setT(at ?? (fr.length ? Date.parse(fr[0].t) : from))
      } finally {
        setLoading(false)
      }
    },
    [api],
  )
  const query = () => void load(Date.now() - PERIODS[period].min * 60_000, Date.now())
  // 처음 열 때 한 번 조회. 고른 알람이 기간 안이면 그 10초 전부터 보여 줌
  const [initial] = useState(() => (sel ? Date.parse(sel.occurred_at) : null))
  useEffect(() => {
    const to = Date.now()
    const from = to - PERIODS[1].min * 60_000
    void load(from, to, initial && initial > from ? initial - 10_000 : undefined)
  }, [load, initial])

  // 재생
  useEffect(() => {
    if (!playing || !range) return
    const id = setInterval(() => {
      setT((x) => {
        const n = x + 200 * speed
        if (n >= range.to) {
          setPlaying(false)
          return range.to
        }
        return n
      })
    }, 200)
    return () => clearInterval(id)
  }, [playing, speed, range])

  // 알람을 고르면 읽음 처리 (WEB-08 ACK_ALARM)
  useEffect(() => {
    if (sel && !sel.acked) void api.requestOperation({ kind: 'ACK_ALARM', target_id: sel.alarm_id, request_key: newRequestKey() }).catch(() => {})
  }, [api, sel])

  const shown = events.filter((e) => (cat === 'ALL' || eventCategory(e) === cat) && (result === 'ALL' || (result === 'BAD') === isBad(e)))
  const marks = shown.filter(isMark)

  const jumpTo = (iso: string) => {
    const at = Date.parse(iso)
    if (range && at >= range.from && at <= range.to) setT(Math.max(range.from, at - 10_000))
    else void load(at - 10 * 60_000, Math.min(Date.now(), at + 10 * 60_000), at - 10_000)
  }

  return (
    <div className={s.a3}>
      <aside aria-label="알람 목록" className={s.alarmSide}>
        <div className={s.sideHead}>
          <div className={s.rowBetween}>
            <h1 className={s.h1} style={{ fontSize: 18 }}>
              알람
            </h1>
            <span className={s.small}>미확인 {ov.alarms.filter((a) => !a.acked).length}</span>
          </div>
          <div className={s.seg4} role="tablist">
            {(['ALL', 'ERROR', 'WARN', 'INFO'] as LevelFilter[]).map((k) => (
              <button key={k} role="tab" aria-selected={level === k} className={level === k ? s.segOn : s.segOff} onClick={() => setLevel(k)}>
                {k === 'ALL' ? '전체' : LEVEL[k][0]}
              </button>
            ))}
          </div>
        </div>
        <ul className={s.alarmList}>
          {alarms.length === 0 && <li className={s.muted} style={{ padding: 16 }}>알람이 없어요</li>}
          {alarms.map((a) => {
            const on = a.alarm_id === selId
            const [lv, tone] = LEVEL[a.level]
            return (
              <li key={a.alarm_id}>
                <button
                  className={`${s.alarmRow} ${on ? s.targetOn : ''}`}
                  style={on ? { boxShadow: `${a.level === 'ERROR' ? '#FF7A66' : a.level === 'WARN' ? C.amber : C.muted} 3px 0 0 inset` } : undefined}
                  aria-current={on || undefined}
                  onClick={() => setParams({ alarm: a.alarm_id })}
                >
                  <span className={s.targetTop}>
                    <span className={s.lvChip} style={toneStyle(tone)}>
                      {lv}
                    </span>
                    <b>{robotName(a.source)}</b>
                    <span className={s.small}>{a.code}</span>
                    {!a.acked && <span className={s.newDot} aria-label="미확인" />}
                    <span className={s.small} style={{ marginLeft: 'auto' }}>
                      {hhmm(a.occurred_at)}
                    </span>
                  </span>
                  <span className={s.targetSub}>
                    {a.message}
                    {a.incident && (a.incident.resolved_at ? ` · ${a.incident.result === 'RESUME' ? '재시도함' : '취소함'}` : ' · 복구 대기')}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </aside>

      <main className={s.a3Main}>
        <div className={s.queryBar}>
          <b style={{ fontSize: 15, marginRight: 8 }}>운영 이력 조회</b>
          <label>
            기간
            <select value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
              {PERIODS.map((p, i) => (
                <option key={p.label} value={i}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            작업 유형
            <select value={cat} onChange={(e) => setCat(e.target.value as EventCategory | 'ALL')}>
              <option value="ALL">전체 (주문·조리·안내·서빙·AMR)</option>
              {(Object.keys(CATEGORY) as EventCategory[]).map((k) => (
                <option key={k} value={k}>
                  {CATEGORY[k].label}
                </option>
              ))}
            </select>
          </label>
          <label>
            처리 결과
            <select value={result} onChange={(e) => setResult(e.target.value as ResultFilter)}>
              {(Object.keys(RESULTS) as ResultFilter[]).map((k) => (
                <option key={k} value={k}>
                  {RESULTS[k]}
                </option>
              ))}
            </select>
          </label>
          <button className={s.primaryBtn} style={{ height: 32, padding: '0 16px' }} onClick={query} disabled={loading}>
            {loading ? '조회 중…' : '조회'}
          </button>
        </div>
        <div className={s.a3Cols}>
          <section aria-label="알람 상세" className={s.alarmDetail}>
            {sel ? <AlarmDetail a={sel} ov={ov} onReplay={() => jumpTo(sel.occurred_at)} /> : <p className={s.muted}>알람을 골라 주세요</p>}
            <h3 className={s.h3}>
              조회 결과 {shown.length}건{range ? ` · ${hhmm(new Date(range.from).toISOString())} ~ ${hhmm(new Date(range.to).toISOString())}` : ''}
            </h3>
            <ul className={s.eventList}>
              {[...shown].reverse().slice(0, 200).map((e) => (
                <li key={e.log_id}>
                  <button onClick={() => jumpTo(e.created_at)}>
                    <span className={s.dot} style={{ background: CATEGORY[eventCategory(e)].color }} />
                    <span className={s.small}>{hhmmss(e.created_at)}</span>
                    <span>{eventText(e)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <Replay frames={frames} range={range} t={t} setT={setT} playing={playing} setPlaying={setPlaying} speed={speed} setSpeed={setSpeed} marks={marks} now={now} />
        </div>
      </main>
    </div>
  )
}

function eventText(e: EventLogRow) {
  const move = `${stateWord(e.entity, e.from_state)} → ${stateWord(e.entity, e.to_state)}`
  if (e.entity === 'ROBOT') return `${robotName(e.entity_id)} ${move}`
  if (e.entity === 'TASK') {
    const type = TASK_TYPE[e.detail?.task_type ?? ''] ?? ''
    return e.from_state ? `${taskNo(e.entity_id)} ${type} ${move}` : `${taskNo(e.entity_id)} ${type} 임무 생성`
  }
  if (e.entity === 'ORDER' && e.from_state) return `${e.entity_id} ${move}`
  return e.message
}

/** 타임라인에 표시할 큰 사건만 (모두 찍으면 빽빽함) */
const isMark = (e: EventLogRow) =>
  e.entity === 'INCIDENT' ||
  e.entity === 'VISIT' ||
  e.entity === 'TABLE' ||
  (e.entity === 'ORDER' && ['ORDERED', 'COMPLETED', 'CANCELED', 'ON_HOLD'].includes(e.to_state ?? '')) ||
  (e.entity === 'ROBOT' && ['CHARGING', 'E_STOP'].includes(e.to_state ?? ''))

function AlarmDetail({ a, ov, onReplay }: { a: Alarm; ov: AdminOverview; onReplay: () => void }) {
  const { run, busy } = useAdmin()
  const inc = a.incident
  const [lv, tone] = LEVEL[a.level]
  const robot = ov.robots.find((r) => r.robot_id === a.source)
  const task = ov.tasks.find((t) => t.task_id === inc?.task_id)
  const open = inc && !inc.resolved_at
  const retry = { kind: 'INCIDENT_RETRY' as const, target_id: a.alarm_id }
  const stop = { kind: 'INCIDENT_STOP' as const, target_id: a.alarm_id }
  const rows: [string, string][] = [
    ['발생 시각', hhmmss(a.occurred_at)],
    ['장치', `${robotName(a.source)}${inc?.device_part ? ` (${inc.device_part})` : ''}`],
  ]
  if (inc) {
    rows.push(['관련 주문', inc.order_id ? `${inc.order_id}${inc.table_id ? ` · ${inc.table_id}번` : ''}` : '—'])
    rows.push(['관련 임무', inc.task_id ? `${taskNo(inc.task_id)}${task ? ` ${task.task_type === 'GUIDE' ? '안내' : task.task_type === 'SERVE' ? '서빙' : '조리'}` : ''}${task?.robot_id ? ` (${robotName(task.robot_id)})` : ''}` : '—'])
    rows.push(['실패 단계', inc.failed_step ?? inc.failed_state ?? '—'])
    rows.push([
      '현재 상태',
      open
        ? robot?.state === 'E_STOP'
          ? '비상 정지 → 복구 대기'
          : '복구 대기'
        : `${inc.result === 'RESUME' ? '재시도 → 이어서 진행' : '작업 취소'} (${hhmm(inc.resolved_at)})`,
    ])
  }
  return (
    <div className={s.alarmBox}>
      <div className={s.cardHead}>
        <span className={s.lvChip} style={toneStyle(tone)}>
          {lv}
        </span>
        <h2 className={s.detailTitle}>
          {robotName(a.source)} · {a.code}
        </h2>
      </div>
      <p className={s.alarmMsg}>{a.message}</p>
      <dl className={s.kv}>
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd style={k === '현재 상태' && open ? { color: C.amber } : undefined}>{v}</dd>
          </div>
        ))}
      </dl>
      {open && inc.hint && <p className={s.small}>재시도 전 확인: {inc.hint}</p>}
      {open && (
        <div className={s.btnRow}>
          <button className={s.primaryBtn} disabled={busy(retry) || busy(stop)} onClick={() => void run(retry, `${a.code} 재시도했어요`)}>
            재시도
          </button>
          <button className={s.outBtn} disabled={busy(retry) || busy(stop)} onClick={() => void run(stop, `${a.code} 작업을 취소했어요`)}>
            작업 취소
          </button>
        </div>
      )}
      <button className={s.linkBtn} onClick={onReplay}>
        이 시점 Replay 보기 →
      </button>
    </div>
  )
}

/* ── Replay ── */

interface ReplayProps {
  frames: ReplayFrame[]
  range: { from: number; to: number } | null
  t: number
  setT: (t: number) => void
  playing: boolean
  setPlaying: (p: boolean) => void
  speed: number
  setSpeed: (n: number) => void
  marks: EventLogRow[]
  now: number
}

const KIND_OF_STATE = (st: string): keyof typeof ROUTE =>
  st === 'E_STOP'
    ? 'error'
    : ['TO_ENTRANCE', 'GUIDING'].includes(st)
      ? 'guide'
      : ['TO_PICKUP', 'QUEUED', 'DOCKED'].includes(st)
        ? 'pick'
        : ['SERVING', 'ARRIVED'].includes(st)
          ? 'serve'
          : st === 'RETURNING'
            ? 'back'
            : 'idle'

function Replay({ frames, range, t, setT, playing, setPlaying, speed, setSpeed, marks }: ReplayProps) {
  const times = useMemo(() => frames.map((f) => Date.parse(f.t)), [frames])
  const idx = useMemo(() => {
    let lo = 0
    let hi = times.length - 1
    if (hi < 0 || t < times[0]) return -1
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1
      if (times[mid] <= t) lo = mid
      else hi = mid - 1
    }
    return lo
  }, [times, t])
  const frame = idx >= 0 ? frames[idx] : null

  const bots: MapBot[] = (frame?.robots ?? []).map((r) => ({
    id: r.robot_id,
    pos: fromMap(r.x, r.y),
    color: ROUTE[KIND_OF_STATE(r.state)],
    label: r.robot_id.replace(/\D/g, ''),
    sub: r.state === 'E_STOP' ? '정지' : '',
  }))
  const routes: MapRoute[] = useMemo(() => {
    if (idx < 0) return []
    const start = Math.max(0, idx - TRAIL_MS / 1000)
    const by = new Map<string, { pts: Pt[]; color: string }>()
    for (let i = start; i <= idx; i++)
      for (const r of frames[i].robots) {
        const e = by.get(r.robot_id) ?? { pts: [], color: ROUTE[KIND_OF_STATE(r.state)] }
        e.pts.push(fromMap(r.x, r.y))
        e.color = ROUTE[KIND_OF_STATE(r.state)]
        by.set(r.robot_id, e)
      }
    return [...by.values()].map((v) => ({ ...v, trail: true }))
  }, [frames, idx])

  const span = range ? range.to - range.from : 1
  const pos = (ms: number) => `${(((ms - (range?.from ?? 0)) / span) * 100).toFixed(2)}%`
  const markTimes = marks.map((m) => Date.parse(m.created_at)).sort((a, b) => a - b)
  const prev = () => setT(markTimes.filter((x) => x < t - 1000).pop() ?? range?.from ?? t)
  const next = () => setT(markTimes.find((x) => x > t + 1000) ?? range?.to ?? t)

  return (
    <section aria-label="Replay" className={s.replay}>
      <div className={s.replayTop}>
        <span className={s.replayBadge}>
          <span className={s.dot} style={{ background: C.amber }} /> REPLAY · {hhmmss(t)}
        </span>
        <span className={s.small}>이동 궤적 실선(최근 30초) · 지도는 A1과 같은 맵 구성도</span>
      </div>
      <div className={s.replayMap}>
        {frame ? (
          <StoreMap3D view="top" width={640} height={520} bots={bots} routes={routes} smooth={false} label={`${hhmmss(t)} 로봇 위치`} />
        ) : (
          <p className={s.muted} style={{ padding: 24 }}>
            이 시간의 위치 기록이 없어요
          </p>
        )}
      </div>
      <div className={s.player}>
        <div className={s.playerRow}>
          <button className={s.sqBtn} aria-label="이전 이벤트" onClick={prev}>
            ‹
          </button>
          <button className={s.playBtn} aria-label={playing ? '일시정지' : '재생'} onClick={() => setPlaying(!playing)}>
            {playing ? '❚❚' : '▶'}
          </button>
          <button className={s.sqBtn} aria-label="다음 이벤트" onClick={next}>
            ›
          </button>
          <b className={s.playTime}>{hhmmss(t)}</b>
          <span className={s.small}>{range ? `/ ${hhmm(new Date(range.from).toISOString())} ~ ${hhmm(new Date(range.to).toISOString())}` : ''}</span>
          <span style={{ flexGrow: 1 }} />
          <span className={s.small}>재생 속도</span>
          {[1, 2, 4].map((n) => (
            <button key={n} className={speed === n ? s.speedOn : s.speedOff} aria-pressed={speed === n} onClick={() => setSpeed(n)}>
              {n}x
            </button>
          ))}
        </div>
        <div
          className={s.timeline}
          role="slider"
          aria-label="재생 위치"
          aria-valuemin={range?.from}
          aria-valuemax={range?.to}
          aria-valuenow={t}
          aria-valuetext={hhmmss(t)}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') setT(Math.min(range?.to ?? t, t + 5000))
            if (e.key === 'ArrowLeft') setT(Math.max(range?.from ?? t, t - 5000))
          }}
          onClick={(e) => {
            if (!range) return
            const box = e.currentTarget.getBoundingClientRect()
            setT(range.from + ((e.clientX - box.left) / box.width) * span)
          }}
        >
          {marks.map((m) => (
            <span key={m.log_id} className={s.mark} style={{ left: pos(Date.parse(m.created_at)), background: CATEGORY[eventCategory(m)].color }} />
          ))}
          <span className={s.playhead} style={{ left: pos(t) }} />
        </div>
        <div className={s.legendRow}>
          {(['order', 'guide', 'charge', 'error'] as EventCategory[]).map((k) => (
            <span key={k}>
              <span className={s.sq} style={{ background: CATEGORY[k].color }} /> {CATEGORY[k].label}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}
