# [수정 2026-11-17] 신규 (UR-03): 안내 중인 손님의 동행 상태.
# Central Control -> AMR, /frybot/guest_track. AI 서버가 AMR 카메라 영상에서
# 얻은 결과(HTTP /ai/result 의 kind = GUEST_TRACK)를 Central Control 이 옮겨 싣는다.
# AMR 은 robot_id 가 자기 것이고 visit_id 가 안내 중인 손님인 것만 쓴다.
# 안내 구간에서 visible = false 이거나 distance 가 follow_pause_dist 보다 크면
# 멈춰서 기다리고(PAUSED_GUEST), guest_timeout 을 넘으면 GUEST_LOST 로 끝낸다.
builtin_interfaces/Time stamp
string robot_id
int64 visit_id
bool visible          # 손님이 카메라에 보이는지
float32 distance      # 로봇에서 손님까지의 거리 (m). visible = false 면 쓰지 않음
