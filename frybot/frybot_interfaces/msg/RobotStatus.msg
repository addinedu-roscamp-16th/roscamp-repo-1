builtin_interfaces/Time stamp
string robot_id
# state: IDLE MOVING TURN DOCKING WAIT_GRANT WAIT_NAV2 NAV2_RETRY PAUSED_GUEST CHARGING
#        YIELD YIELD_BLOCKED (양보 후진 / 뒤가 막힘)
#        WAIT_FMS (no heartbeat from the Task Manager)  E_STOP (held by the emergency-stop channel)
#        or, while the serving arm works, the arm job name (LOAD UNLOAD COLLECT_DISHES RETURN_DISHES)
string state
float64 x
float64 y
float64 yaw
float32 battery       # 0..100 (percent)
bool charging
string task_id
int32 plan_version
int32 reached_index   # index of last reached waypoint of the active route (-1 none)
string node_id        # roadmap node the robot reached last ('' until it reached one)
string arm_state      # IDLE or current arm job
# error: '' when nothing is wrong, else a name from frybot_control/device_state.py ERROR:
#        COMMUNICATION_ERROR (no heartbeat)  EMERGENCY_STOP  DRIVE_ERROR (Nav2 could not drive the last segment)
# A robot that is not localised yet (measured map, no AMCL pose) sends no status at all and shows as OFFLINE.
string error
