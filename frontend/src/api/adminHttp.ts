import type {
  AdminApi,
  AdminOverview,
  EventLogRow,
  OperationAccepted,
  OperationStatus,
  ReplayFrame,
} from './adminContract'
import { ApiError, type ApiErrorCode } from './contract'

/**
 * 관리자 화면 ↔ 실제 Web Service. VITE_API_MODE=http 일 때 씁니다.
 * WEB-07/08/09 는 I/F 목록 경로 그대로, 이력·Replay 는 [제안] 경로입니다.
 */
export function createHttpAdminApi(base = '/api'): AdminApi {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    let res: Response
    try {
      res = await fetch(base + path, {
        method,
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw new ApiError('NETWORK')
    }
    if (!res.ok) {
      let code: ApiErrorCode = 'UNKNOWN'
      try {
        const j = (await res.json()) as { error?: { code?: string } }
        if (j.error?.code) code = j.error.code as ApiErrorCode
      } catch {
        /* 본문 없음 */
      }
      throw new ApiError(code, res.status)
    }
    return (await res.json()) as T
  }
  const range = (q: { from: string; to: string }) =>
    `from=${encodeURIComponent(q.from)}&to=${encodeURIComponent(q.to)}`

  return {
    getOverview: () => call<AdminOverview>('GET', '/admin/overview'),
    requestOperation: (req) => call<OperationAccepted>('POST', '/admin/operations', req),
    getOperation: (id) => call<OperationStatus>('GET', `/admin/operations/${encodeURIComponent(id)}`),
    getEvents: (q) => call<EventLogRow[]>('GET', `/admin/events?${range(q)}`),
    getReplay: (q) => call<ReplayFrame[]>('GET', `/admin/replay?${range(q)}`),

    subscribeOverview(onData, onConnection) {
      let ws: WebSocket | null = null
      let closed = false
      let retry = 0
      let timer: ReturnType<typeof setTimeout> | null = null
      let last = -1
      const deliver = (o: AdminOverview) => {
        if (o.version <= last) return
        last = o.version
        onData(o)
      }
      const open = () => {
        if (closed) return
        const url = new URL(`${base}/ws`, window.location.href)
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
        ws = new WebSocket(url)
        ws.onopen = () => {
          retry = 0
          onConnection?.(true)
          ws?.send(JSON.stringify({ type: 'subscribe', topics: [{ admin: true }] }))
          // 연결·재연결 때 스냅샷으로 누락 복원
          call<AdminOverview>('GET', '/admin/overview').then(deliver, () => {})
        }
        ws.onmessage = (ev) => {
          try {
            const m = JSON.parse(ev.data as string) as { type: string; version: number; data: AdminOverview }
            if (m.type === 'admin') deliver({ ...m.data, version: m.version })
          } catch {
            /* 형식이 다른 메시지는 무시 */
          }
        }
        ws.onclose = () => {
          if (closed) return
          onConnection?.(false)
          timer = setTimeout(open, Math.min(10_000, 500 * 2 ** retry++))
        }
      }
      open()
      return () => {
        closed = true
        if (timer) clearTimeout(timer)
        ws?.close()
      }
    },
  }
}
