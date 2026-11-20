import type { CSSProperties, ReactNode } from 'react'
import {
  AISLE_L,
  AISLE_U,
  BAYS,
  CHARGERS,
  COOK_ARMS,
  ENTRANCE_X,
  GREET,
  PICKUPS,
  STANDBY,
  TABLES,
  ZONES,
  type Pt,
} from '../api/storeLayout'

/**
 * 관리자 매장 지도 (시안 Map3D). 맵 구성도 좌표(cm)를 그대로 쓰고, CSS 3D로 비스듬히 보거나 위에서 봅니다.
 * 화면 데이터는 부모가 정리해 넘깁니다(로봇 위치·경로·로봇팔 카드).
 */

const S = 3.2 // px per cm
const W = 232 * S // 조리대(벽 밖)까지
const H = 100 * S

export interface MapBot {
  id: string
  pos: Pt
  color: string
  label: string
  sub: string
  selected?: boolean
  /** 하얀 점선 테두리 (일시 중단) */
  dashed?: boolean
}
export interface MapRoute {
  pts: Pt[]
  color: string
  dim?: boolean
  /** 지나온 길(실선, 얇게) */
  trail?: boolean
}
export interface MapArm {
  cook: 'FRY' | 'WOK'
  title: string
  chip: string
  color: string
  order: string
  step: string
  pct: number
  state: string
}

interface Props {
  view: '3d' | 'top'
  width: number
  height: number
  bots: MapBot[]
  routes: MapRoute[]
  arms?: MapArm[]
  /** 강조할 테이블 */
  tables?: number[]
  onSelect?: (id: string) => void
  /** 위치가 바뀔 때 부드럽게 (실시간 2 Hz) */
  smooth?: boolean
  label?: string
}

export function StoreMap3D({ view, width, height, bots, routes, arms = [], tables = [], onSelect, smooth = true, label }: Props) {
  const is3d = view === '3d'
  const s3 = Math.min((width - 40) / 808, (height - 110) / 394)
  const sTop = Math.min((width - 32) / W, (height - 40) / (H + 40))
  const stage: CSSProperties = {
    position: 'absolute',
    left: '50%',
    top: '50%',
    width: W,
    height: H,
    marginLeft: -W / 2,
    marginTop: -H / 2 + (is3d ? 24 : 0),
    transformStyle: 'preserve-3d',
    transition: 'transform 0.7s ease',
    transform: is3d ? `rotateX(52deg) rotateZ(-22deg) scale(${s3.toFixed(3)})` : `scale(${sTop.toFixed(3)})`,
  }

  return (
    <div
      role="img"
      aria-label={label ?? '매장 지도'}
      style={{
        position: 'relative',
        width,
        height,
        overflow: 'hidden',
        background: '#121620',
        perspective: 2000,
        perspectiveOrigin: '50% 40%',
      }}
    >
      <div style={stage}>
        <Floor tables={tables} />
        <svg width={W} height={H} aria-hidden="true" style={{ position: 'absolute', left: 0, top: 0, overflow: 'visible', transform: 'translateZ(1px)' }}>
          {[AISLE_U, AISLE_L].map((y) => (
            <line key={y} x1={32 * S} x2={166 * S} y1={y * S} y2={y * S} stroke="#5B9BFF" strokeOpacity={0.5} strokeWidth={1.5} strokeDasharray="6 5" />
          ))}
          {routes.map((r, i) => (
            <polyline
              key={i}
              points={r.pts.map(([x, y]) => `${x * S},${y * S}`).join(' ')}
              fill="none"
              stroke={r.color}
              strokeWidth={r.trail ? 2 : 3}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={r.dim ? 0.12 : r.trail ? 0.55 : 1}
            />
          ))}
        </svg>
        <Furniture tables={tables} />
        {bots.map((b) => (
          <Box
            key={b.id}
            x={b.pos[0] - 5}
            y={b.pos[1] - 5}
            w={10}
            d={10}
            h={12}
            col={shade(b.color)}
            label={b.label}
            sub={b.sub}
            r={5}
            ring={b.selected ? '#FFFFFF' : b.dashed ? '#F5B942' : `${b.color}55`}
            smooth={smooth}
            onClick={onSelect ? () => onSelect(b.id) : undefined}
            title={b.id}
          />
        ))}
        {arms.map((a) => (
          <ArmCard key={a.cook} arm={a} is3d={is3d} s3={s3} />
        ))}
      </div>
      {!is3d && arms.length > 0 && (
        <div style={{ position: 'absolute', left: 14, top: 12, display: 'flex', gap: 8 }}>
          {arms.map((a) => (
            <span
              key={a.cook}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderRadius: 999, border: `1.5px solid ${a.color}`, background: '#0F1218E6', fontSize: 12 }}
            >
              <span style={{ width: 8, height: 8, borderRadius: 4, background: a.color }} />
              <b>{a.title}</b> {a.step}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── 바닥 ── */

function Zone({ r, style, label, color }: { r: readonly [number, number, number, number]; style?: CSSProperties; label?: string; color?: string }) {
  const [x0, y0, x1, y1] = r
  return (
    <div style={{ position: 'absolute', boxSizing: 'border-box', left: x0 * S, top: y0 * S, width: (x1 - x0) * S, height: (y1 - y0) * S, ...style }}>
      {label && (
        <span style={{ position: 'absolute', left: 4, bottom: 3, fontSize: 9, fontWeight: 700, color, whiteSpace: 'nowrap' }}>{label}</span>
      )}
    </div>
  )
}

function Floor({ tables }: { tables: number[] }) {
  const pick = '#F59E0B'
  return (
    <>
      <Zone
        r={[0, 0, 200, 100]}
        style={{
          backgroundColor: '#1C2230',
          backgroundImage: 'linear-gradient(#232A3A 1px, transparent 1px), linear-gradient(90deg, #232A3A 1px, transparent 1px)',
          backgroundSize: `${10 * S}px ${10 * S}px`,
        }}
      />
      <Zone r={ZONES.charge} style={{ background: '#16263F' }} label="충전 구역" color="#5B9BFF" />
      <Zone r={[12.2, 0.6, 31.8, 99.4]} style={{ border: '1.5px dashed #C2410C', borderRadius: 4 }} label="충전대 앞 통로" color="#C2410C" />
      <Zone r={ZONES.cook} style={{ background: '#2A1E14' }} label="조리 구역 · 1대씩" color="#C2410C" />
      {TABLES.map((t) => {
        const [x0, y0, x1, y1] = t.rect
        const pad = t.seats === 2 ? 6 : 7
        const on = tables.includes(t.id)
        return (
          <Zone
            key={t.id}
            r={[x0 - pad, Math.max(0.6, y0), x1 + pad, Math.min(99.4, y1)]}
            style={{ background: on ? '#3A2A16' : '#2A2620', borderRadius: 3, outline: on ? '2px solid #F59E0B' : undefined }}
          />
        )
      })}
      {BAYS.map((b, i) => (
        <Zone key={`b${i}`} r={b} style={{ border: '1.5px dashed #22C55E', borderRadius: 4, background: '#22C55E14' }} label="비켜 서는 곳" color="#16A34A" />
      ))}
      {STANDBY.map((b, i) => (
        <Zone key={`s${i}`} r={b} style={{ border: '1.5px dashed #22C55E', borderRadius: 4, background: '#22C55E14' }} label="대기" color="#16A34A" />
      ))}
      <Zone r={[88, 44, 114, 56]} style={{ border: '1.5px dashed #5B9BFF', borderRadius: 4 }} label="연결 통로" color="#5B9BFF" />
      {/* 손님 맞이 */}
      <Zone r={[GREET[0] - 4.5, GREET[1] - 4.5, GREET[0] + 4.5, GREET[1] + 4.5]} style={{ border: '2px dashed #8B5CF6', borderRadius: '50%' }} />
      <Zone r={[13, 25, 32, 31]} label="손님 맞이" color="#8B5CF6" />
      {/* 받는 곳 */}
      {(['FRY', 'WOK'] as const).map((k) => {
        const [x, y] = PICKUPS[k]
        return <Zone key={k} r={[x - 4, y - 4, x + 4, y + 4]} style={{ border: `2px solid ${pick}`, borderRadius: '50%' }} />
      })}
      <Zone r={[166, AISLE_U + 5, 200, AISLE_U + 11]} label="튀김 받는 곳" color={pick} />
      <Zone r={[166, AISLE_L + 5, 200, AISLE_L + 11]} label="볶음밥 받는 곳" color={pick} />
      {/* 테이블 앞 정차점 */}
      {TABLES.map((t) => (
        <div
          key={`stop${t.id}`}
          style={{ position: 'absolute', left: t.stop[0] * S - 4, top: t.stop[1] * S - 4, width: 8, height: 8, borderRadius: 4, background: '#22C55E', transform: 'translateZ(2px)' }}
        />
      ))}
      <div
        style={{
          position: 'absolute',
          left: ENTRANCE_X * S - 20,
          top: -26,
          width: 40,
          textAlign: 'center',
          fontSize: 11,
          fontWeight: 700,
          color: '#8B5CF6',
          transform: 'translateZ(2px)',
        }}
      >
        입구
      </div>
    </>
  )
}

/* ── 가구·벽 (상자) ── */

const P = {
  wall: ['#4A5670', '#3A4560', '#2E374D'],
  table: ['#8B6B55', '#6E5442', '#5C4536'],
  chair: ['#D9D2C7', '#B5ADA2', '#9C948A'],
  bench: ['#C9CFDA', '#A3ACBD', '#8A93A5'],
  charge: ['#5B9BFF', '#1D4ED8', '#1E40AF'],
}

function Furniture({ tables }: { tables: number[] }) {
  const out: ReactNode[] = []
  for (const t of TABLES) {
    t.chairs.forEach(([x0, y0, x1, y1], i) =>
      out.push(<Box key={`c${t.id}-${i}`} x={x0 + 0.4} y={y0 + 0.4} w={x1 - x0 - 0.8} d={y1 - y0 - 0.8} h={5} col={P.chair} r={3} />),
    )
    const [x0, y0, x1, y1] = t.rect
    const on = tables.includes(t.id)
    out.push(
      <Box
        key={`t${t.id}`}
        x={x0}
        y={y0}
        w={x1 - x0}
        d={y1 - y0}
        h={14}
        col={on ? ['#F59E0B', '#B45309', '#92400E'] : P.table}
        label={`${t.id}번`}
        sub={`${t.seats}인`}
        fs={11}
      />,
    )
  }
  // 벽 (위쪽 벽은 입구 12~32를 비움)
  out.push(<Box key="w1" x={-2} y={-2} w={14} d={2} h={14} col={P.wall} />)
  out.push(<Box key="w2" x={32} y={-2} w={168} d={2} h={14} col={P.wall} />)
  out.push(<Box key="w3" x={-2} y={100} w={202} d={2} h={14} col={P.wall} />)
  out.push(<Box key="w4" x={-2} y={0} w={2} d={100} h={14} col={P.wall} />)
  out.push(<Box key="w5" x={200} y={-2} w={4} d={104} h={22} col={['#2A2A2E', '#1C1C20', '#121214']} />)
  CHARGERS.forEach((c, i) => {
    const [, y0, , y1] = c.rect
    out.push(<Box key={c.id} x={2} y={y0 + 2} w={8} d={y1 - y0 - 4} h={4} col={P.charge} label={`⚡${i + 1}`} fs={10} />)
  })
  out.push(<Box key="bench" x={205} y={10} w={8} d={80} h={16} col={P.bench} label="조리대" fg="#E7EAF0" fs={9} />)
  return <>{out}</>
}

function shade(c: string): [string, string, string] {
  const n = parseInt(c.slice(1), 16)
  const f = (k: number) =>
    '#' +
    [16, 8, 0]
      .map((sh) => Math.round(((n >> sh) & 255) * k).toString(16).padStart(2, '0'))
      .join('')
  return [c, f(0.75), f(0.6)]
}

interface BoxProps {
  x: number
  y: number
  w: number
  d: number
  h: number
  col: readonly string[]
  r?: number
  label?: string
  sub?: string
  fs?: number
  fg?: string
  ring?: string
  smooth?: boolean
  onClick?: () => void
  title?: string
}

/** 바닥 위에 선 직육면체 (윗면 + 네 옆면) */
function Box({ x, y, w, d, h, col, r = 2, label, sub, fs = 11, fg = '#FFFFFF', ring, smooth, onClick, title }: BoxProps) {
  const px = { w: w * S, d: d * S }
  const face: CSSProperties = { position: 'absolute', boxSizing: 'border-box' }
  return (
    <div
      onClick={onClick}
      title={title}
      style={{
        position: 'absolute',
        left: x * S,
        top: y * S,
        width: px.w,
        height: px.d,
        transformStyle: 'preserve-3d',
        transition: smooth ? 'left 0.5s linear, top 0.5s linear' : undefined,
        cursor: onClick ? 'pointer' : undefined,
      }}
    >
      <div style={{ ...face, left: 0, top: px.d, width: px.w, height: h, transformOrigin: 'top', transform: 'rotateX(90deg)', background: col[1] }} />
      <div style={{ ...face, left: 0, top: -h, width: px.w, height: h, transformOrigin: 'bottom', transform: 'rotateX(-90deg)', background: col[1] }} />
      <div style={{ ...face, left: -h, top: 0, width: h, height: px.d, transformOrigin: 'right', transform: 'rotateY(90deg)', background: col[2] }} />
      <div style={{ ...face, left: px.w, top: 0, width: h, height: px.d, transformOrigin: 'left', transform: 'rotateY(-90deg)', background: col[2] }} />
      <div
        style={{
          ...face,
          left: 0,
          top: 0,
          width: px.w,
          height: px.d,
          transform: `translateZ(${h}px)`,
          background: col[0],
          borderRadius: r,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1,
          boxShadow: ring ? `0 0 0 4px ${ring}` : undefined,
        }}
      >
        {label && <span style={{ fontSize: fs, fontWeight: 700, color: fg, whiteSpace: 'nowrap', lineHeight: 1.1 }}>{label}</span>}
        {sub && <span style={{ fontSize: 9, color: fg, opacity: 0.85, whiteSpace: 'nowrap', lineHeight: 1.1 }}>{sub}</span>}
      </div>
    </div>
  )
}

/** 벽 밖 조리 로봇팔과, 그 위에 뜨는 상태 카드 */
function ArmCard({ arm, is3d, s3 }: { arm: MapArm; is3d: boolean; s3: number }) {
  const [ax, ay] = COOK_ARMS[arm.cook]
  const cx = 221
  const cy = ay - 3
  const t = `translateZ(44px) rotateZ(22deg) rotateX(-52deg) scale(${(1 / s3).toFixed(3)}) translate(-72%, -100%) translateY(-10px)`
  return (
    <>
      <Box x={ax - 6} y={ay - 6} w={12} d={12} h={30} col={shade(arm.color)} label={arm.cook === 'FRY' ? '튀김' : '웍'} sub={arm.state} fs={10} r={4} ring={`${arm.color}66`} />
      <div
        aria-label={`${arm.title} ${arm.chip}`}
        style={{
          position: 'absolute',
          left: cx * S,
          top: cy * S,
          width: 168,
          boxSizing: 'border-box',
          padding: '8px 10px',
          borderRadius: 10,
          display: is3d ? 'flex' : 'none',
          flexDirection: 'column',
          gap: 5,
          background: '#0F1218F2',
          border: `1.5px solid ${arm.color}`,
          color: '#E7EAF0',
          boxShadow: '0 6px 18px #00000066',
          transformOrigin: '0 0',
          transition: 'transform 0.7s ease',
          transform: t,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 9, height: 9, borderRadius: 5, background: arm.color }} />
          <b style={{ fontSize: 13 }}>{arm.title}</b>
          <span style={{ marginLeft: 'auto', padding: '1px 8px', borderRadius: 999, fontSize: 11, fontWeight: 700, background: arm.color, color: '#0F1218' }}>
            {arm.chip}
          </span>
        </div>
        <span style={{ fontSize: 12 }}>{arm.order}</span>
        <div style={{ height: 6, background: '#2A3142', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ width: `${arm.pct}%`, height: 6, background: arm.color }} />
        </div>
        <span style={{ fontSize: 11, color: '#A3ACBD' }}>{arm.step}</span>
      </div>
    </>
  )
}
