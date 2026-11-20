import {
  NoTableAvailableError,
  type GuideStatus,
  type KioskApi,
  type StaffCallReason,
  type TableAssignment,
} from './types'

/**
 * 실제 백엔드(FastAPI)용 구현. 백엔드가 아직 없으므로 VITE_API_MODE=http 일 때만 씁니다.
 *
 *   POST   /api/kiosk/assignments          {partySize}  → TableAssignment (409: 빈 자리 없음)
 *   DELETE /api/kiosk/assignments/{id}
 *   WS     /api/kiosk/assignments/{id}/guide            → GuideStatus JSON 메시지
 *   POST   /api/staff-calls                {reason, source:"kiosk"}
 */
export function createHttpKioskApi(base = '/api'): KioskApi {
  return {
    async assignTable(partySize) {
      const res = await fetch(`${base}/kiosk/assignments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partySize }),
      })
      if (res.status === 409) throw new NoTableAvailableError()
      if (!res.ok) throw new Error(`assignTable failed: ${res.status}`)
      return (await res.json()) as TableAssignment
    },

    watchGuide(assignmentId, onStatus) {
      const url = new URL(
        `${base}/kiosk/assignments/${encodeURIComponent(assignmentId)}/guide`,
        window.location.href,
      )
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(url)
      ws.onmessage = (ev) => onStatus(JSON.parse(ev.data as string) as GuideStatus)
      return () => ws.close()
    },

    async cancelAssignment(assignmentId) {
      await fetch(`${base}/kiosk/assignments/${encodeURIComponent(assignmentId)}`, {
        method: 'DELETE',
      })
    },

    async callStaff(reason: StaffCallReason) {
      await fetch(`${base}/staff-calls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason, source: 'kiosk' }),
      })
    },
  }
}
