import { createContext, useContext } from 'react'
import type { AdminApi, AdminOverview, OperationRequest } from '../api'

export type Notify = (text: string, tone?: 'ok' | 'error') => void
export type RunOp = (req: Omit<OperationRequest, 'request_key'>, doneText: string) => Promise<boolean>

export interface AdminCtx {
  api: AdminApi
  /** 서버에서 받은 현황. 아직 못 받았으면 빈 현황 */
  ov: AdminOverview
  /** 서버에서 현황을 한 번이라도 받았는지 */
  hasData: boolean
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

/** 서버에서 아무것도 못 받았을 때 화면 틀만 그리는 빈 현황 */
export const EMPTY_OVERVIEW: AdminOverview = {
  server_time: new Date(0).toISOString(),
  ros_connected: false,
  robots: [],
  tables: [],
  orders: [],
  tasks: [],
  alarms: [],
  version: -1,
}
