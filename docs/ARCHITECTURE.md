# FryBot 하드웨어·소프트웨어 아키텍처

## 하드웨어 구성

| 장비 | 역할 | 실행 소프트웨어 |
| --- | --- | --- |
| 관제 PC | 방문·주문에 따른 임무 배정, 지도·상태 관리, 시뮬레이션 실행 | `frybot_control`, `frybot_web`, `frybot_bringup` |
| Pinky AMR | 손님 안내, 서빙, 식기 회수의 이동 수행 | `frybot_mobile`, Nav2 |
| JetCobot 조리 팔 | 조리 동작 실행. 조리 팔 두 대는 소프트웨어에서 `cook_arm_a`, `cook_arm_b`로 구분 | `frybot_arm` |
| 키오스크·테이블 태블릿·관리자 단말 | 방문 접수, 주문, 관제 화면 표시 | React 프론트엔드 |
| API·DB 실행 호스트 | FastAPI와 MySQL 실행 | `backend/api`, `backend/db`. 실제 배포 호스트는 팀 배포 환경 기준 |

## 소프트웨어 모듈과 폴더

| 아키텍처 모듈 | 저장소 경로 | 코드 모듈·패키지 |
| --- | --- | --- |
| 사용자 화면 | `frontend/` | `frontend/src/kiosk`, `frontend/src/table`, `frontend/src/admin` |
| 백엔드 API·DB | `backend/` | `backend/api/main.py`, `backend/db`, `api/openapi.yaml` |
| AMR 주행·장비 제어 | `frybot/frybot_mobile/` | `frybot_mobile` |
| 로봇 모델 | `frybot/frybot_description/` | `frybot_description` |
| 관제·임무 배정 | `frybot/frybot_control/` | `frybot_control`의 `central_control`, `task_manager` |
| 공통 ROS 2 계약 | `frybot/frybot_interfaces/` | `frybot_interfaces`의 메시지·서비스·액션 |
| 통합 기동 | `frybot/frybot_bringup/` | `frybot_bringup` |
| 시뮬레이션 | `frybot/frybot_sim/` | `frybot_sim` |
| ROS 웹 | `frybot/frybot_web/` | `frybot_web` |
| JetCobot 조리 제어 | `frybot/frybot_arm/` | `frybot_arm`의 `master_controller`, `arm_controller`, `cooking.launch.py` |

## 연동 경계

- 프론트엔드와 FastAPI의 HTTP 계약은 `api/openapi.yaml`로 맞춘다. 현재 ROS 시뮬레이션용 웹 서버는 자체 HTTP 경로를 사용하며, 전체 React → FastAPI → ROS 2 연동은 통합 검증 대상이다.
- ROS 관제는 `frybot_interfaces`를 공유하고 조리 작업을 `/frybot_arm/arm_job` 액션으로 보낸다. 통합 시뮬레이션 launch가 `frybot_arm`을 불러오므로 저장소 루트에서 `colcon build --base-paths frybot`로 ROS 패키지 8개를 빌드한다.
- 시뮬레이션과 실기기 실행은 별도 ROS 도메인을 사용하는 절차를 따른다. [시뮬레이션·실기기 실행 명령](../FRYBOT_COMMANDS.md)
