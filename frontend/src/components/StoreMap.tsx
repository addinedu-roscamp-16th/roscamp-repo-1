/**
 * 키오스크(K2)용 간단한 매장 배치도. 입구에서 배정된 테이블까지 점선 경로를 그립니다.
 * 테이블 위치는 시안(K2_table-assigned.html)의 좌표를 그대로 씁니다.
 */

import { COL_X, ENTRANCE, ROW_Y, STORE_LAYOUT, TABLE_H, TABLE_W, routeTo } from './storeLayout'

export function StoreMap({ tableId }: { tableId: string }) {
  const route = routeTo(tableId)
  return (
    <svg
      width="360"
      height="300"
      viewBox="0 0 360 300"
      role="img"
      aria-label={`매장 배치도. 입구에서 ${tableId} 테이블까지 가는 길`}
      style={{ fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      {STORE_LAYOUT.map((t) => {
        const x = COL_X[t.col]
        const y = ROW_Y[t.row]
        const on = t.id === tableId
        return (
          <g key={t.id}>
            <rect x={x} y={y} width={TABLE_W} height={TABLE_H} rx="14" fill={on ? '#F0640F' : '#DDE1E7'} />
            {on && (
              <text x={x + TABLE_W / 2} y={y + 33} textAnchor="middle" fontSize="20" fontWeight="800" fill="#FFFFFF">
                {t.id}
              </text>
            )}
          </g>
        )
      })}
      {route && (
        <path d={route} stroke="#F0640F" strokeWidth="4" strokeDasharray="2 10" strokeLinecap="round" fill="none" />
      )}
      <circle cx={ENTRANCE.x} cy={ENTRANCE.y} r="12" fill="#191C21" />
      <circle cx={ENTRANCE.x} cy={ENTRANCE.y} r="5" fill="#FFFFFF" />
      <text x="100" y="268" fontSize="16" fontWeight="700" fill="#3A404B">
        입구 · 지금 여기
      </text>
    </svg>
  )
}
