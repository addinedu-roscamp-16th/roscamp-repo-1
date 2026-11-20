import { createContext, useContext } from 'react'
import type { AdminApi, AdminOverview, OperationRequest } from '../api'

export type Notify = (text: string, tone?: 'ok' | 'error') => void
export type RunOp = (req: Omit<OperationRequest, 'request_key'>, doneText: string) => Promise<boolean>

export interface AdminCtx {
  api: AdminApi
  ov: AdminOverview | null
  connected: boolean
  /** 화면 시계(ms). 가짜 서버면 서버 시각 */
  now: number
  run: RunOp
  /** 같은 조작이 진행 중인지 (버튼 끄기) */
  busy: (req: Omit<OperationRequest, 'request_key'>) => boolean
  notify: Notify
}

export const Ctx = createContext<AdminCtx | null>(null)

export function useAdmin() {
  const c = useContext(Ctx)
  if (!c) throw new Error('AdminApp 안에서만 씁니다')
  return c
}

export const opKey = (r: Omit<OperationRequest, 'request_key'>) => `${r.kind}:${r.target_id}:${r.params?.status ?? ''}`
