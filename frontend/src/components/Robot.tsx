import { useId, type CSSProperties } from 'react'

/**
 * 로봇 캐릭터. 시안(screens/K1~K4, T1~T5)의 인라인 SVG를 그대로 옮겼습니다.
 *  - wave    : 한 손을 들고 반기는 모습 (K1, T1, T5)
 *  - peek    : 머리만, 눈이 오른쪽을 봄 (K2 진행 카드)
 *  - wait    : 두 손을 모으고 땀방울 (K3)
 *  - guide   : 팔로 길을 가리키고 가슴 화면에 테이블 번호 (K4)
 *  - confirm : 두 팔을 내리고 아래를 봄 (T2)
 *  - cook    : 뚜껑 두 개를 들고 땀방울 (T3)
 *  - serve   : 큰 뚜껑 하나와 반짝이, 웃는 눈 (T4)
 */
export type RobotPose = 'wave' | 'peek' | 'wait' | 'guide' | 'confirm' | 'cook' | 'serve'

interface Props {
  pose: RobotPose
  /** guide 자세일 때 가슴 화면에 띄울 글자 (예: "T5") */
  label?: string
  width?: number
  height?: number
  className?: string
  style?: CSSProperties
}

export function Robot({ pose, label = '', width, height, className, style }: Props) {
  // 한 화면에 로봇이 여러 개 있어도 그라데이션 id가 겹치지 않도록
  const p = 'rb' + useId().replace(/[^a-zA-Z0-9]/g, '')
  const u = (name: string) => `url(#${p}${name})`
  const isPeek = pose === 'peek'

  return (
    <svg
      width={width ?? (isPeek ? 56 : 210)}
      height={height ?? (isPeek ? 50 : 252)}
      viewBox={isPeek ? '20 8 160 128' : '0 0 200 240'}
      aria-hidden="true"
      className={className}
      style={style}
    >
      <defs>
        <radialGradient id={`${p}w`} cx="0.34" cy="0.28" r="0.85">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.55" stopColor="#F0F2F6" />
          <stop offset="1" stopColor="#C3CAD5" />
        </radialGradient>
        <linearGradient id={`${p}arm`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.5" stopColor="#E8EBF0" />
          <stop offset="1" stopColor="#B8C0CC" />
        </linearGradient>
        <radialGradient id={`${p}o`} cx="0.32" cy="0.28" r="0.8">
          <stop offset="0" stopColor="#FFC59E" />
          <stop offset="0.45" stopColor="#F57A2E" />
          <stop offset="1" stopColor="#B93C0A" />
        </radialGradient>
        <linearGradient id={`${p}v`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3C4456" />
          <stop offset="1" stopColor="#0F1218" />
        </linearGradient>
        <radialGradient id={`${p}e`} cx="0.5" cy="0.4" r="0.65">
          <stop offset="0" stopColor="#EEFCFF" />
          <stop offset="0.45" stopColor="#8BE6FF" />
          <stop offset="1" stopColor="#22AEE0" />
        </radialGradient>
        <linearGradient id={`${p}m`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#E9ECF1" />
          <stop offset="1" stopColor="#9EA7B4" />
        </linearGradient>
        <radialGradient id={`${p}sh`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#3A2A1E" stopOpacity="0.32" />
          <stop offset="1" stopColor="#3A2A1E" stopOpacity="0" />
        </radialGradient>
        <filter id={`${p}glow`} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="3.2" />
        </filter>
        <filter id={`${p}soft`} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>

      {!isPeek && <Body pose={pose} label={label} u={u} />}
      <Head u={u} />
      <Face pose={pose} u={u} />
    </svg>
  )
}

type U = (name: string) => string

const BODY_PATH =
  'M58 132 h84 a16 16 0 0 1 16 16 v54 a24 24 0 0 1 -24 24 h-68 a24 24 0 0 1 -24 -24 v-54 a16 16 0 0 1 16 -16z'

function Body({ pose, label, u }: { pose: RobotPose; label: string; u: U }) {
  const torso = (
    <>
      <path d={BODY_PATH} fill={u('w')} />
      <ellipse cx="100" cy="138" rx="42" ry="7" fill="#7E8896" opacity="0.35" filter={u('soft')} />
      <rect x="88" y="120" width="24" height="18" rx="7" fill={u('m')} />
    </>
  )
  const shadow = <ellipse cx="100" cy="229" rx="72" ry="12" fill={u('sh')} />

  if (pose === 'wave' || pose === 'confirm') {
    return (
      <>
        {shadow}
        {pose === 'wave' ? (
          <>
            <rect x="32" y="146" width="20" height="46" rx="10" fill={u('arm')} />
            <rect x="152" y="90" width="20" height="52" rx="10" fill={u('arm')} transform="rotate(24 162 142)" />
          </>
        ) : (
          <>
            <rect x="30" y="146" width="20" height="46" rx="10" fill={u('arm')} transform="rotate(8 40 148)" />
            <rect x="150" y="146" width="20" height="46" rx="10" fill={u('arm')} transform="rotate(-8 160 148)" />
          </>
        )}
        {torso}
        <rect x="78" y="160" width="44" height="10" rx="5" fill={u('o')} />
        <rect x="84" y="161.5" width="16" height="3" rx="1.5" fill="#FFFFFF" opacity="0.55" />
      </>
    )
  }

  if (pose === 'wait' || pose === 'cook' || pose === 'serve') {
    // 쟁반 위에 뚜껑(cloche)을 든 자세. 시안마다 꼭지 높이·하이라이트 위치가 조금씩 다릅니다.
    const knobY = pose === 'wait' ? 126 : 124
    const hl = pose === 'wait' ? { dx: 0, y: 138 } : { dx: -0.8, y: 137.9 }
    return (
      <>
        {shadow}
        {torso}
        <ellipse cx="100" cy="158" rx="66" ry="6" fill="#5A4636" opacity="0.18" filter={u('soft')} />
        {pose === 'serve' ? (
          <>
            <path d="M70 150 a30 30 0 0 1 60 0z" fill={u('w')} />
            <circle cx="100" cy="116" r="4" fill={u('m')} />
            <ellipse cx="88.0" cy="133.5" rx="5" ry="3" fill="#FFFFFF" opacity="0.9" />
          </>
        ) : (
          <>
            <path d="M52 150 a22 22 0 0 1 44 0z" fill={u('w')} />
            <circle cx="74" cy={knobY} r="4" fill={u('m')} />
            <ellipse cx={66 + hl.dx} cy={hl.y} rx="5" ry="3" fill="#FFFFFF" opacity="0.9" />
            <path d="M104 150 a22 22 0 0 1 44 0z" fill={u('w')} />
            <circle cx="126" cy={knobY} r="4" fill={u('m')} />
            <ellipse cx={118 + hl.dx} cy={hl.y} rx="5" ry="3" fill="#FFFFFF" opacity="0.9" />
          </>
        )}
        <rect x="36" y="148" width="128" height="10" rx="5" fill={u('m')} />
        <rect x="28" y="152" width="20" height="32" rx="10" fill={u('arm')} />
        <rect x="152" y="152" width="20" height="32" rx="10" fill={u('arm')} />
      </>
    )
  }

  // guide
  return (
    <>
      {shadow}
      <rect x="30" y="148" width="20" height="46" rx="10" fill={u('arm')} transform="rotate(12 40 150)" />
      <rect x="156" y="130" width="20" height="50" rx="10" fill={u('arm')} transform="rotate(-72 162 140)" />
      {torso}
      <rect x="68" y="150" width="64" height="38" rx="12" fill={u('v')} />
      <g fontFamily="'Noto Sans KR', sans-serif" fontSize="21" fontWeight="800" textAnchor="middle">
        <text x="100" y="176" fill="#5FD8FF" opacity="0.8" filter={u('glow')}>
          {label}
        </text>
        <text x="100" y="176" fill="#DDF8FF">
          {label}
        </text>
      </g>
    </>
  )
}

function Head({ u }: { u: U }) {
  return (
    <>
      <path d="M100 42 v-18" stroke={u('m')} strokeWidth="5" strokeLinecap="round" />
      <circle cx="100" cy="20" r="9" fill={u('o')} />
      <ellipse cx="97" cy="16" rx="3" ry="2" fill="#FFFFFF" opacity="0.75" />
      <rect x="24" y="68" width="18" height="32" rx="9" fill={u('o')} />
      <rect x="158" y="68" width="18" height="32" rx="9" fill={u('o')} />
      <ellipse cx="30" cy="76" rx="3" ry="5" fill="#FFFFFF" opacity="0.5" />
      <rect x="36" y="38" width="128" height="92" rx="42" fill={u('w')} />
      <ellipse cx="74" cy="48" rx="22" ry="6" fill="#FFFFFF" opacity="0.9" filter={u('soft')} />
      <rect x="49" y="53" width="102" height="62" rx="29" fill={u('v')} />
      <path d="M62 64 q38 -14 76 0" stroke="#FFFFFF" strokeWidth="5" strokeLinecap="round" fill="none" opacity="0.16" />
    </>
  )
}

function Cheeks({ u }: { u: U }) {
  return (
    <>
      <circle cx="61" cy="99" r="6" fill="#FF8A5C" opacity="0.55" filter={u('glow')} />
      <circle cx="139" cy="99" r="6" fill="#FF8A5C" opacity="0.55" filter={u('glow')} />
    </>
  )
}

/** 둥근 사각 눈 2개 (발광 + 본체 + 하이라이트) */
function RoundEyes({ x1, x2, y, u }: { x1: number; x2: number; y: number; u: U }) {
  return (
    <>
      <g opacity="0.85" filter={u('glow')}>
        <rect x={x1} y={y} width="16" height="22" rx="8" fill="#5FD8FF" />
        <rect x={x2} y={y} width="16" height="22" rx="8" fill="#5FD8FF" />
      </g>
      <rect x={x1} y={y} width="16" height="22" rx="8" fill={u('e')} />
      <rect x={x2} y={y} width="16" height="22" rx="8" fill={u('e')} />
      <ellipse cx={x1 + 5} cy={y + 5} rx="2.5" ry="3" fill="#FFFFFF" />
      <ellipse cx={x2 + 5} cy={y + 5} rx="2.5" ry="3" fill="#FFFFFF" />
    </>
  )
}

function Face({ pose, u }: { pose: RobotPose; u: U }) {
  switch (pose) {
    case 'wave':
      return (
        <>
          <RoundEyes x1={71} x2={113} y={68} u={u} />
          <path d="M88 98 q12 9 24 0" stroke="#8BE6FF" strokeWidth="4" fill="none" strokeLinecap="round" />
          <Cheeks u={u} />
        </>
      )
    case 'confirm':
      return (
        <>
          <RoundEyes x1={67} x2={109} y={74} u={u} />
          <path d="M88 98 q12 9 24 0" stroke="#8BE6FF" strokeWidth="4" fill="none" strokeLinecap="round" />
          <Cheeks u={u} />
        </>
      )
    case 'peek':
      return <RoundEyes x1={77} x2={119} y={70} u={u} />
    case 'wait':
    case 'cook':
      return (
        <>
          <g opacity="0.85" filter={u('glow')}>
            <rect x="67" y="72" width="24" height="8" rx="4" fill="#5FD8FF" />
            <rect x="109" y="72" width="24" height="8" rx="4" fill="#5FD8FF" />
          </g>
          <rect x="67" y="72" width="24" height="8" rx="4" fill={u('e')} />
          <rect x="109" y="72" width="24" height="8" rx="4" fill={u('e')} />
          <circle cx="100" cy="99" r="5" fill="none" stroke="#8BE6FF" strokeWidth="3.5" />
          <path d="M174 30 q9 13 0 20 q-9 -7 0 -20z" fill="#8FD3FF" />
          <ellipse cx="172" cy="42" rx="1.6" ry="2.6" fill="#FFFFFF" opacity="0.8" />
        </>
      )
    case 'guide':
    case 'serve':
      return (
        <>
          <g opacity="0.85" filter={u('glow')}>
            <path d="M68 85 q11 -15 22 0" stroke="#5FD8FF" strokeWidth="6" fill="none" strokeLinecap="round" />
            <path d="M110 85 q11 -15 22 0" stroke="#5FD8FF" strokeWidth="6" fill="none" strokeLinecap="round" />
          </g>
          <path d="M68 85 q11 -15 22 0" stroke={u('e')} strokeWidth="6" fill="none" strokeLinecap="round" />
          <path d="M110 85 q11 -15 22 0" stroke={u('e')} strokeWidth="6" fill="none" strokeLinecap="round" />
          <path d="M86 97 q14 13 28 0" stroke="#8BE6FF" strokeWidth="4" fill="none" strokeLinecap="round" />
          <Cheeks u={u} />
          {pose === 'serve' && (
            <>
              <path d="M176 40 l3 8 l8 3 l-8 3 l-3 8 l-3 -8 l-8 -3 l8 -3z" fill="#FFC59E" />
              <path d="M24 30 l2 5 l5 2 l-5 2 l-2 5 l-2 -5 l-5 -2 l5 -2z" fill="#FFC59E" />
            </>
          )}
        </>
      )
  }
}
