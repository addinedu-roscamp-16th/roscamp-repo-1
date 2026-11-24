builtin_interfaces/Time stamp
string task_id
string task_type      # GUIDE SERVE COLLECT COOK MOVE
# state, by task type (all of them are published by frybot_control/fleet_core.py):
#   any AMR task : ASSIGNED ... DONE | SUSPENDED (reason = cause) RESUMED REASSIGNED CANCELED
#                  [수정 2026-11-18] SUSPENDED 의 reason: OFFLINE, E_STOP, PAUSED, NAV2_FAILED 등과
#                  PLAN_FAIL(같은 목적지 계획 실패가 20초 넘게 이어짐, RETRY_TASK 로 재개)
#   GUIDE        : AT_START ARRIVED
#   SERVE        : LOADED SERVING DELIVERED
#                  [수정 2026-11-18] SERVING = 적재 뒤 테이블행 구간을 처음 나아갔을 때 한 번 (State Diagram v4)
#   COLLECT      : COLLECTED RETURNED
#   COOK         : COOKING READY (reason = pick-up place) | SUSPENDED RESUMED CANCELED
string state
string robot_id
int64 visit_id
int64 order_id
int64 item_id
int32 table_id
int32 plan_version
string reason
