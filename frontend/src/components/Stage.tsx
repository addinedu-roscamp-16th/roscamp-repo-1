import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import styles from './Stage.module.css'

interface Props {
  /** 시안 기준 크기. K·T 화면은 932×572, 관리자 화면은 1440×900 */
  width: number
  height: number
  children: ReactNode
  /** 관리자 화면처럼 어두운 배경·직각 모서리가 필요할 때 */
  backdrop?: string
  frameStyle?: CSSProperties
}

/**
 * 시안 크기(px) 그대로 그린 화면을 기기 화면에 꽉 차게 비율을 유지해 늘립니다.
 * README: "실제 기기 해상도에 맞게 늘려서 구현해 주세요."
 */
export function Stage({ width, height, children, backdrop, frameStyle }: Props) {
  const [scale, setScale] = useState(() => fit(width, height))

  useEffect(() => {
    const onResize = () => setScale(fit(width, height))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [width, height])

  return (
    <div className={styles.backdrop} style={backdrop ? { background: backdrop } : undefined}>
      <div style={{ width: width * scale, height: height * scale }}>
        <div
          className={styles.frame}
          style={{ width, height, transform: `scale(${scale})`, ...frameStyle }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

function fit(w: number, h: number) {
  if (typeof window === 'undefined' || !window.innerWidth) return 1
  return Math.min(window.innerWidth / w, window.innerHeight / h)
}
