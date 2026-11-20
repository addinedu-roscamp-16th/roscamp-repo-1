import {
  ApiError,
  type ApiErrorCode,
  type CreateOrderResponse,
  type CreateVisitResponse,
  type DiningTable,
  type EndVisitResponse,
  type FrybotApi,
  type MenuItem,
  type ServerEvent,
  type SubscribeMessage,
  type Topic,
  type VisitSnapshot,
} from './contract'

/**
 * 실제 Web Service(FastAPI) 연결. VITE_API_MODE=http 일 때 씁니다.
 * 경로는 I/F 목록 그대로이고, 개발 서버가 /api 를 백엔드로 넘깁니다(vite.config.ts).
 */
export function createHttpApi(base = '/api'): FrybotApi {
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
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
  }

  return {
    createVisit: (req) => call<CreateVisitResponse>('POST', '/visits', req),
    getVisit: (id) => call<VisitSnapshot>('GET', `/visits/${encodeURIComponent(id)}/status`),
    getMenu: (tableId) => call<MenuItem[]>('GET', tableId == null ? '/menu' : `/menu?table_id=${tableId}`),
    createOrder: (req) => call<CreateOrderResponse>('POST', '/orders', req),
    endVisit: (id, request_key) =>
      call<EndVisitResponse>('POST', `/visits/${encodeURIComponent(id)}/end`, { request_key }),
    getTables: () => call<DiningTable[]>('GET', '/tables'),
    callStaff: (source, table_id) => call<void>('POST', '/staff-calls', { source, table_id: table_id ?? null }),

    subscribe(topics: Topic[], onEvent: (e: ServerEvent) => void) {
      let ws: WebSocket | null = null
      let closed = false
      let retry = 0
      let retryTimer: ReturnType<typeof setTimeout> | null = null
      const last = new Map<string, number>()
      const keyOf = (e: ServerEvent) => (e.type === 'visit' ? `v:${e.data.visit_id}` : `t:${e.data.table_id}`)

      const deliver = (e: ServerEvent) => {
        const k = keyOf(e)
        if ((last.get(k) ?? -1) >= e.version) return // 역순·중복은 버림
        last.set(k, e.version)
        onEvent(e)
      }

      // 연결·재연결 때 스냅샷으로 누락을 복원
      const resync = async () => {
        for (const tp of topics) {
          try {
            if ('visit_id' in tp) {
              const v = await call<VisitSnapshot>('GET', `/visits/${encodeURIComponent(tp.visit_id)}/status`)
              deliver({ type: 'visit', version: v.version, data: v })
            } else {
              const ts = await call<DiningTable[]>('GET', '/tables')
              const t = ts.find((x) => x.table_id === tp.table_id)
              if (t) deliver({ type: 'table', version: last.get(`t:${t.table_id}`) ?? 0, data: t })
            }
          } catch {
            /* 다음 재연결 때 다시 */
          }
        }
      }

      const open = () => {
        if (closed) return
        const url = new URL(`${base}/ws`, window.location.href)
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
        ws = new WebSocket(url)
        ws.onopen = () => {
          retry = 0
          const msg: SubscribeMessage = { type: 'subscribe', topics }
          ws?.send(JSON.stringify(msg))
          void resync()
        }
        ws.onmessage = (ev) => {
          try {
            deliver(JSON.parse(ev.data as string) as ServerEvent)
          } catch {
            /* 형식이 다른 메시지는 무시 */
          }
        }
        ws.onclose = () => {
          if (closed) return
          retryTimer = setTimeout(open, Math.min(10_000, 500 * 2 ** retry++))
        }
      }
      open()

      return () => {
        closed = true
        if (retryTimer) clearTimeout(retryTimer)
        ws?.close()
      }
    },
  }
}
