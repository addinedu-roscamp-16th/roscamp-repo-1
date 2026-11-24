# FryBot JetCobot 6축 IK 및 시뮬레이터 도입 참고

2026-11-24 · 향후 검토

## 기존 모델과 웹 IK 레퍼런스

로컬 `~/addinedu/sim/jetcobot_gz/`에 `jetcobot.urdf`, `world.sdf`, `run_sim.sh`, `log_joints.py`, `play_fry.py`가 있다. 비교 실험에서 URDF의 팔 6축과 그리퍼 관절을 구분하고, 실제 장비로 이어갈 때 제어기 관절 이름과 대조한다. 팔 관절의 URDF 순서는 `joint2_to_joint1`, `joint3_to_joint2`, `joint4_to_joint3`, `joint5_to_joint4`, `joint6_to_joint5`, `joint6output_to_joint6`이다.

웹 데모는 목표 위치·자세 입력, 복수 IK 해 선택, 현재 자세에 가까운 해 우선 표시, FK 오차 표시를 참고할 수 있다. 원본 해석적 IK는 자체 관절 축과 링크 치수에 맞춰져 있으므로 JetCobot에 적용하려면 URDF의 축 방향, 링크 변환, 영점, 관절 한계, 공구 중심점(TCP)부터 대조한다. 위치 전용 모드는 공구 방향을 샘플링한다. 소스 재사용 시 MIT 라이선스 고지를 포함한다. [원본 저장소](https://github.com/arjunvallyath234/6DOF_robotic_arm) · [웹 데모](https://arjunvallyath234.github.io/6DOF_robotic_arm/6DOF_ik_tester.html)

## 용도별 후보

| 후보 | FryBot에서 시험할 범위 | 참고 |
| --- | --- | --- |
| Gazebo + ROS 2 + MoveIt 2 | 기존 JetCobot URDF를 기준으로 계획 그룹과 TCP를 설정하고 관절 한계, 자기 충돌, 작업대 및 튀김 바스켓 충돌을 포함한 접근·이탈 경로 검증 | [MoveIt 설정](https://moveit.picknik.ai/humble/doc/examples/setup_assistant/setup_assistant_tutorial.html) |
| Unreal Engine | FryBot 작업대와 로봇팔의 시연 및 기록 재생. 먼저 ROS 관절 상태를 Control Rig의 6개 관절에 적용하고, 화면에서 목표를 직접 조작해야 할 때 Full-Body IK를 별도로 평가 | [Control Rig Full-Body IK](https://dev.epicgames.com/documentation/unreal-engine/control-rig-full-body-ik-in-unreal-engine) |
| NVIDIA Isaac Sim | 카메라 기반 바스켓 위치 추정이나 조명·가림 검증이 필요할 때 ROS 2 Bridge와 관절 모델 연동 검토 | [Isaac Sim ROS 2 관절 제어](https://docs.isaacsim.omniverse.nvidia.com/latest/ros2_tutorials/robot_control/tutorial_ros2_manipulation.html) |
| 웹 IK 화면 | 교육·디버깅용으로 목표와 실제 TCP, 후보 관절 자세, FK 오차를 빠르게 확인 | [참고 소스](https://github.com/arjunvallyath234/6DOF_robotic_arm/blob/main/6DOF_ik_tester.html) |

## PoC 재개 순서

1. 기존 Gazebo에서 홈 자세와 각 관절 단독 움직임을 기록한다. 공통 기록에는 관절 이름, 라디안 각도, 타임스탬프를 넣고 TCP 참조 좌표계와 위치·자세를 함께 보관한다.
2. 동일한 기록을 Unreal에서 재생한다. URDF에서 읽은 이름으로 매핑하고, 영점과 축 부호를 관절별로 확인한다. 월드 좌표를 넘길 때 ROS의 미터와 Unreal의 센티미터, 좌표계 방향을 변환한다.
3. Gazebo와 Unreal에서 홈, 바스켓 접근, 파지, 들어 올리기, 이탈 자세의 TCP를 비교한다. 위치 오차와 회전 오차를 별도로 기록한다. 허용 기준은 바스켓과 그리퍼의 실제 여유에 맞춰 정한다.
4. MoveIt에서 위 작업의 계획 결과와 도달 불가, 관절 한계 초과, 작업대 또는 바스켓 충돌 사례를 확인한다. Unreal·웹 화면은 동일한 관절 기록으로 계획 결과를 재생할 수 있도록 연동한다. 카메라 검증이 필요해지면 같은 장면과 자세를 Isaac Sim 후보에 적용한다.
