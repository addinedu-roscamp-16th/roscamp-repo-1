import { ENTRANCE_X, STORE_H, STORE_W, TABLES, ZONES, guideRoute, tableName } from '../api/storeLayout'

/**
 * 키오스크(K2)용 매장 배치도. 맵 구성도(200 × 100 cm)를 그대로 줄여 그리고,
 * 입구에서 배정된 테이블 앞까지 안내 로봇이 가는 길을 점선으로 표시합니다.
 */

const S = 1.86 // px per cm
const OX = 4
const OY = 92
const px = (x: number) => OX + x * S
const py = (y: number) => OY + y * S
const ENT_Y = OY - 30 // "지금 여기" 표시 위치 (매장 위쪽 바깥)

type Rect = readonly [number, number, number, number]
const R = ([x0, y0, x1, y1]: Rect, rx = 4, fill = '#DDE1E7', key?: string) => (
  <rect key={key} x={px(x0)} y={py(y0)} width={(x1 - x0) * S} height={(y1 - y0) * S} rx={rx} fill={fill} />
)

export function StoreMap({ tableId }: { tableId: number }) {
  const route = guideRoute(tableId)
  const d = route
    ? `M${px(ENTRANCE_X)} ${ENT_Y} ` + route.map(([x, y]) => `L${px(x)} ${py(y)}`).join(' ')
    : null

  return (
    <svg
      width="380"
      height="300"
      viewBox="0 0 380 300"
      role="img"
      aria-label={`매장 배치도. 입구에서 ${tableName(tableId)} 테이블까지 가는 길`}
      style={{ fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      {/* 매장 바닥 */}
      <rect x={px(0)} y={py(0)} width={STORE_W * S} height={STORE_H * S} rx="6" fill="#FFFFFF" />
      {R(ZONES.charge, 0, '#E8EEF6')}
      {R(ZONES.cook, 0, '#FFF1E7')}
      <text x={px(183)} y={py(52)} textAnchor="middle" fontSize="14" fontWeight="700" fill="#C2410C">
        조리
      </text>
      <rect
        x={px(0)}
        y={py(0)}
        width={STORE_W * S}
        height={STORE_H * S}
        rx="6"
        fill="none"
        stroke="#3A404B"
        strokeWidth="2"
      />
      {/* 입구: 위쪽 벽을 비움 */}
      <rect x={px(12)} y={py(0) - 2} width={20 * S} height="4" fill="#F4F5F7" />

      {/* 테이블 */}
      {TABLES.map((t) => {
        const on = t.id === tableId
        const [x0, y0, x1, y1] = t.rect
        return (
          <g key={t.id}>
            {t.chairs.map((c, i) => R(c, 3, on ? '#FFD2B5' : '#ECEEF2', `c${i}`))}
            {R(t.rect, 4, on ? '#F0640F' : '#DDE1E7')}
            <text
              x={px((x0 + x1) / 2)}
              y={py((y0 + y1) / 2) + (on ? 6 : 5)}
              textAnchor="middle"
              fontSize={on ? 16 : 13}
              fontWeight="800"
              fill={on ? '#FFFFFF' : '#5C6370'}
            >
              {t.id}
            </text>
          </g>
        )
      })}

      {/* 안내 경로 */}
      {d && (
        <path d={d} stroke="#F0640F" strokeWidth="4" strokeDasharray="2 9" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      )}

      {/* 지금 여기 */}
      <circle cx={px(ENTRANCE_X)} cy={ENT_Y} r="12" fill="#191C21" />
      <circle cx={px(ENTRANCE_X)} cy={ENT_Y} r="5" fill="#FFFFFF" />
      <text x={px(ENTRANCE_X) + 22} y={ENT_Y + 6} fontSize="16" fontWeight="700" fill="#3A404B">
        입구 · 지금 여기
      </text>
    </svg>
  )
}
