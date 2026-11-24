# [수정 2026-11-17] 신규 (UR-17, 19): 로봇팔 한 대의 상태·오류 보고.
# 팔 제어기 -> Task Manager, /fleet/arm_status, 약 2 Hz.
#   조리 팔: frybot_arm 의 arm_controller (arm_id = cook_arm_a | cook_arm_b)
#   서빙 팔: frybot_mobile 의 mobile_controller (arm_id = 로봇 id, 예: pinky1)
# 조리 팔의 보고가 3초 넘게 끊기면 관제는 그 팔을 OFFLINE 으로 표시한다.
# 지금의 팔 제어기는 대역이라 error 는 항상 비어 있다.
builtin_interfaces/Time stamp
string arm_id
string state          # frybot_control/device_state.py STATE 이름: IDLE COOKING ARM_OPERATING FAULT_HANDLING ...
string job            # 수행 중인 ArmJob 의 job 이름 ('' = 없음)
string task_id        # 그 작업의 임무 id ('' = 없음)
string error          # '' = 이상 없음, 아니면 device_state.py ERROR 이름 (ARM_ERROR GRIPPER_ERROR ...)
