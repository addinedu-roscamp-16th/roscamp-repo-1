import type { CartLine, MenuItem, Order, TableApi, TableState } from './tableTypes'

/**
 * 테이블 태블릿용 실제 백엔드(FastAPI) 구현. VITE_API_MODE=http 일 때만 씁니다.
 *
 *   GET    /api/menu                               → MenuItem[]
 *   POST   /api/tables/{tableId}/orders  {lines}   → Order
 *   WS     /api/tables/{tableId}/state             → TableState JSON (바뀔 때마다)
 *   POST   /api/tables/{tableId}/end-session
 *   POST   /api/staff-calls  {reason:"help", source:"table", tableId}
 */
export function createHttpTableApi(base = '/api'): TableApi {
  const t = (id: string) => `${base}/tables/${encodeURIComponent(id)}`
  const json = async <T,>(res: Response) => {
    if (!res.ok) throw new Error(`${res.url} → ${res.status}`)
    return (await res.json()) as T
  }

  return {
    async getMenu() {
      return json<MenuItem[]>(await fetch(`${base}/menu`))
    },

    async placeOrder(tableId: string, lines: CartLine[]) {
      return json<Order>(
        await fetch(`${t(tableId)}/orders`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lines }),
        }),
      )
    },

    watchTable(tableId, onState) {
      const url = new URL(`${t(tableId)}/state`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(url)
      ws.onmessage = (ev) => onState(JSON.parse(ev.data as string) as TableState)
      return () => ws.close()
    },

    async endSession(tableId) {
      const res = await fetch(`${t(tableId)}/end-session`, { method: 'POST' })
      if (!res.ok) throw new Error(`end-session → ${res.status}`)
    },

    async callStaff(tableId) {
      await fetch(`${base}/staff-calls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'help', source: 'table', tableId }),
      })
    },
  }
}
