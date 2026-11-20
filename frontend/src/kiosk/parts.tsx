import type { ReactNode } from 'react'
import c from '../components/customer.module.css'
import s from './kiosk.module.css'

export function BrandMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect width="28" height="28" rx="9" fill="#F0640F" />
      <circle cx="14" cy="14" r="6" fill="none" stroke="#FFFFFF" strokeWidth="3" />
    </svg>
  )
}

export function TopBar({ step, onCallStaff }: { step: 1 | 2 | 3; onCallStaff: () => void }) {
  return (
    <div className={c.topBar}>
      <BrandMark />
      <span className={c.brand}>OneTeam 레스토랑</span>
      <div className={s.steps} role="img" aria-label={`3단계 중 ${step}단계`}>
        {[1, 2, 3].map((n) => (
          <span key={n} className={`${s.step} ${n <= step ? s.stepOn : ''}`} />
        ))}
      </div>
      <button type="button" className={c.staffBtn} onClick={onCallStaff}>
        직원 호출
      </button>
    </div>
  )
}

export function RobotPanel({ bubble, children }: { bubble: string; children: ReactNode }) {
  return (
    <div className={c.robotPanel}>
      <div className={c.bubble}>{bubble}</div>
      {children}
    </div>
  )
}

export function ProgressBar({ value, muted, label }: { value: number; muted?: boolean; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  return (
    <div
      className={c.bar}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
    >
      <div className={`${c.barFill} ${muted ? c.barFillMuted : ''}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="9" fill="#1F9254" />
      <path
        d="M6 10.2 l2.6 2.6 L14 7.4"
        stroke="#FFFFFF"
        strokeWidth="2.4"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function BellIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 16 V11 a6 6 0 0 1 12 0 v5 l1.5 2 h-15z" fill="none" stroke="#5C6370" strokeWidth="2" strokeLinejoin="round" />
      <path d="M10 20.5 a2 2 0 0 0 4 0" fill="none" stroke="#5C6370" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
