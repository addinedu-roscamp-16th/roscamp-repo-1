import type { AdminOverview, AmrView, ArmView } from '../api'
import { TABLES, homeOf, toMap } from '../api/storeLayout'

/**
 * 서버에서 아무것도 못 받았을 때 보여 줄 매장 구성.
 * 테이블·로봇이 몇 개인지는 맵 구성도(layout.py)로 이미 알지만, 상태는 모르므로
 * 화면은 hasData=false 일 때 상태 칸을 "연결 안 됨 / 확인 안 됨"으로 바꿔 보여 줍니다.
 */
export const AMR_IDS = ['pinky1', 'pinky2', 'pinky3']
export const ARM_IDS = { FRY: 'cook_arm_a', WOK: 'cook_arm_b' } as const

const NEVER = new Date(0).toISOString()

export const SKELETON_OVERVIEW: AdminOverview = {
  server_time: NEVER,
  ros_connected: false,
  robots: [
    ...AMR_IDS.map((id): AmrView => {
      const [x, y] = toMap(homeOf(id))
      return {
        type: 'AMR',
        robot_id: id,
        state: 'IDLE',
        hold_state: null,
        task_id: null,
        last_seen_at: NEVER,
        pose: { x, y, yaw: 0 },
        battery_pct: 0,
        is_charging: false,
        speed: 0,
        path: [],
      }
    }),
    ...(['FRY', 'WOK'] as const).map(
      (cook): ArmView => ({
        type: 'ARM',
        robot_id: ARM_IDS[cook],
        cook_type: cook,
        state: 'IDLE',
        hold_state: null,
        task_id: null,
        last_seen_at: NEVER,
        cook: null,
      }),
    ),
  ],
  tables: TABLES.map((t) => ({
    table_id: t.id,
    code: `T${t.id}`,
    seats: t.seats,
    status: 'AVAILABLE',
    visit_id: null,
    visit: null,
  })),
  orders: [],
  tasks: [],
  alarms: [],
  version: -1,
}
