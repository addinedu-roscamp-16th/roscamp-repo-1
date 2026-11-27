# FryBot 실행 명령

`frybot/` 폴더의 패키지를 받아서 빌드하고 실행하는 명령입니다. 전체 구조와 인터페이스는 [frybot/README.md](frybot/README.md)를 참고합니다.

- 작성: 2026-11-19
- 갱신: 2026-11-27 — 개인 작업 공간의 2026-11-27 코드로 `frybot/`을 덮어쓴 것에 맞춤. 관리자 API 경로(`/api/admin/operations`), `auto_home` 기본 `false`와 자동 위치 추정, 지도 `test_map_v05`·`test_map_v06`(후진 도킹), 로봇별 바퀴 치수, `cmd_vel_timeout`, 서빙 팔, 손님 추적(`frybot_ai`), 천장 카메라를 반영했습니다.
- 환경: Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, Nav2 Jazzy
- 확인(2026-11-27): 이 저장소의 `frybot/`만으로 새 작업 공간에서 빌드(9개 패키지), pytest, `fleet_bench --scenario rush --check`(기본 조합)를 확인했습니다. 시뮬·실기기 런치는 이 문서를 쓰면서 다시 실행하지 않았습니다.
- `<run_id>`, `<방향>`처럼 꺾쇠로 적은 부분은 실제 값으로 바꿉니다.
- 원본 작업 공간의 `docs/`와 `scripts/`(전체 종료 스크립트, 카메라 녹화, 실행 기록 등)는 이 저장소에 없습니다. `frybot/README.md`의 `docs/...`, `scripts/...`, `runs/...`, `archive/...` 링크와 경로는 열리지 않습니다.

## 1. 받기와 빌드

작업 공간의 `src/` 아래에 저장소를 받습니다. colcon이 하위 폴더의 패키지를 찾아 빌드합니다.

```bash
mkdir -p ~/frybot_ws/src && cd ~/frybot_ws/src
git clone -b Juheon_Lee https://github.com/addinedu-roscamp-16th/roscamp-repo-1.git

cd ~/frybot_ws
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src/roscamp-repo-1/frybot --ignore-src -r -y   # 처음 한 번
colcon build --symlink-install --packages-up-to frybot_bringup
source install/setup.bash
```

| 하려는 것 | 명령 |
|---|---|
| 전체 빌드 | `colcon build --symlink-install --packages-up-to frybot_bringup` |
| 패키지 하나 | `colcon build --symlink-install --packages-select frybot_control` |
| 손님 추적(AI 서버)까지 | `colcon build --symlink-install --packages-up-to frybot_bringup frybot_ai` |
| 최신 코드 받기 | `cd ~/frybot_ws/src/roscamp-repo-1 && git pull` 후 다시 빌드 |
| 터미널을 열 때마다 | `cd ~/frybot_ws && source install/setup.bash` |
| 단위 시험 | `python3 -m pytest src/roscamp-repo-1/frybot` |

- 패키지: `frybot_interfaces`, `frybot_control`, `frybot_web`, `frybot_mobile`, `frybot_arm`, `frybot_sim`, `frybot_ai`, `frybot_bringup`, `frybot_description`.
- 외부 저장소(`pinky_pro`, `mycobot_ros2`)는 빌드와 실행에 필요하지 않습니다. 쓰는 모델 파일은 `frybot_description`에 들어 있습니다.
- 저장소에 다른 팀원의 패키지가 함께 있으면 `--packages-up-to frybot_bringup`을 꼭 붙여 FryBot 패키지만 빌드합니다.

## 2. 시뮬레이션

시뮬은 전용 도메인 74에서 돕니다(`net:=sim`이 기본). 켜져 있는 실제 Pinky(도메인 73)와 서로 보이지 않습니다. 시뮬에 `ros2 topic`, `ros2 service` 같은 명령을 쓰는 터미널에서는 먼저 `export ROS_DOMAIN_ID=74`를 실행합니다. 시나리오 실행기와 웹 화면은 HTTP만 써서 필요 없습니다.

### 가상 매장 (접수부터 서빙·회수까지)

```bash
# 터미널 1: 경량 시뮬 + RViz
ros2 launch frybot_bringup sim.launch.py
# 터미널 2: 자동 시나리오 (demo | normal | rush | single)
ros2 run frybot_sim scenario --scenario demo
```

### 실측 지도 (노드 간 이동)

```bash
ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v04
```

- 지도: `test_map_v001`, `test_map_v002`, `test_map_v03`, `test_map_v04`, `test_map_v05`, `test_map_v06` (설명은 `frybot/README.md`의 "지도" 표)
- 매장·손님·조리 팔·AI 서버와 8090 화면은 뜨지 않습니다. 이동 명령은 4장을 봅니다.
- 자세를 직접 움직이는 방식이라 Nav2·라이다·AMCL을 거치지 않고, 소요 시간이 실기기와 다릅니다.

### 실측 지도 서빙 시험 (`test_map_v04`·`v05`·`v06`)

이 지도들은 `roadmap.json`에 `stations`와 `docks`가 있어 서빙 임무(`SERVE`)를 받습니다.

```bash
# 터미널 1
ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v06 robots:=2 serving_robots:=pinky1 rviz:=false
# 터미널 2 (export ROS_DOMAIN_ID=74 먼저)
ros2 service call /fms/submit_task frybot_interfaces/srv/SubmitTask "{task_type: 'SERVE', table_id: 1, menu: 'FRIED'}"
grep -E "TASK_|ARM_" runs/<run_id>/events.csv
```

- `test_map_v06`: 조리대 도크 `D1_STOP`, 충전소 `H1`~`H3`(홈·대기), 테이블 1 정지 노드 `B2`. 도크는 모두 후진 도킹(`"dock_backwards": true`). 실기기 확인 전 초안입니다.
- `serving_robots`를 주면 SERVE·COLLECT를 그 로봇에만 맡깁니다(비우면 모든 로봇).
- 서빙 팔 전달까지 보려면 `serving_arm:=real`을 붙이고 `/pinky1/serving_arm/arm_job` 액션 서버(실물 `serving_arm_driver` 또는 가짜 서버)를 띄웁니다. 서버가 없으면 주행 전 팔 접기가 `ARM_OFFLINE`으로 실패해 출발하지 않고 임무가 `SUSPENDED`가 됩니다.

### Gazebo + Nav2 (가상 매장 전용)

```bash
ros2 launch frybot_bringup gazebo.launch.py
ros2 launch frybot_bringup gazebo.launch.py gui:=false rviz:=false   # 화면 없이
```

### 조리 팔 대역만

```bash
ros2 launch frybot_arm cooking.launch.py
```

### 자주 쓰는 런치 인자

| 인자 | 기본값 | 내용 |
|---|---|---|
| `map_id` | `proto` | 지도 이름 |
| `robots` | `3` | 로봇 대수 (가상 매장은 7대까지) |
| `scheduler` | `min_cost_eta_rh` | `min_cost`, `min_cost_eta`, `priority_greedy`, `fifo_nearest` |
| `planner` | `sipp` | `ccbs`, `cooperative_astar`, `independent_astar` |
| `rviz` | `true` | RViz 표시 |
| `serving_arm` | 없음 | `real`이면 서빙 팔 작업을 `/<로봇>/serving_arm/arm_job`으로 넘김 |
| `serving_robots` | 없음 | SERVE·COLLECT를 맡길 로봇(쉼표) |
| `cook_time_scale` | `20` | 조리 시간 축소 |

전체 인자는 `frybot/README.md`의 "런치 인자" 표에 있습니다.

## 3. 실기기 (Pinky)

실기기는 도메인 73을 씁니다. 로봇·서빙 팔 주소와 계정은 저장소 밖의 `~/.config/frybot/robots.yaml`에 등록합니다. 비밀번호가 들어가므로 저장소에 올리지 않습니다.

```bash
mkdir -p ~/.config/frybot
cp ~/frybot_ws/src/roscamp-repo-1/frybot/frybot_bringup/config/robots.example.yaml ~/.config/frybot/robots.yaml
chmod 600 ~/.config/frybot/robots.yaml      # 그다음 주소·계정을 채움
```

### 배포와 점검

`robot_remote`의 배포 원본 기본값은 `~/frybot_ws/src/frybot`입니다. 이 저장소 구조에서는 `--source`로 경로를 알려 줍니다.

| 하려는 것 | 명령 |
|---|---|
| 접속·설치 상태 점검 | `ros2 run frybot_bringup robot_remote --all --check` |
| 코드와 지도를 모든 로봇에 배포 | `ros2 run frybot_bringup robot_remote --all --deploy --source ~/frybot_ws/src/roscamp-repo-1/frybot` |
| 일부 로봇만 배포 | `ros2 run frybot_bringup robot_remote pinky2 pinky3 --deploy --source ~/frybot_ws/src/roscamp-repo-1/frybot` |
| 실제로 실행될 내용만 출력 | 위 명령에 `--dry-run`을 붙임 |
| 로봇에 남은 프로그램 정지 | `ros2 run frybot_bringup robot_remote --all --stop` |

코드나 지도를 고쳤으면 빌드 → 배포 → 점검 순서로 합니다. 로봇 프로그램이 도는 중에는 배포하지 않습니다.

### 기동

```bash
# 등록된 로봇 전부. 초기 자세 없이 띄우면 로봇이 라이다 스캔으로 자기 자세를 찾음
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v05
# 로봇과 출발 자세 지정 (로봇:노드[:방향(도)])
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v05 robots:=pinky1,pinky2 poses:=pinky1:W1:<방향>,pinky2:W2:<방향>
# 한 대만, RViz 없이
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v05 robots:=pinky1 rviz:=false
# RViz만 따로
ros2 launch frybot_bringup fleet_rviz.launch.py robots:=pinky1,pinky2,pinky3
```

- `map_id`는 필수이고 실측 지도여야 합니다. PC와 Pinky가 같은 `map_id`를 써야 합니다.
- `poses`는 로봇이 실제로 서 있는 자리에 맞춥니다. 0도는 +x, 180도는 -x입니다. 생략하면 `auto_localize`가 스캔으로 자세를 찾고(로그 `auto localisation OK`·`OK_SAVED`·`OK_HOME`·`OK_CAMERA`), 실패하면(`AMBIGUOUS`·`NO_MATCH`) RViz의 **2D Pose Estimate**로 정합니다.
- `auto_home` 기본은 `false`입니다(2026-11-20부터). 연결된 로봇은 지금 자리에서 대기합니다. `auto_home:=true`면 위치가 잡힌 로봇이 출발 노드로 한 번 움직입니다.
- 관제 PC의 천장 카메라 노드(`ceiling_locator`)가 기본으로 뜹니다. 카메라가 없으면 `ceiling_camera:=false`를 붙입니다(로봇도 카메라 판정을 기다리지 않음).
- 종료는 런치 터미널에서 Ctrl-C입니다. 로봇 쪽도 함께 멈춥니다. 로봇에 프로그램이 남았으면 `robot_remote --all --stop`을 씁니다.
- Pinky 안에서 직접 띄울 때: `ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 map_id:=test_map_v05`
- Pinky 안에서 드라이버만(수동 조종·센서 점검용): `ros2 launch frybot_mobile bringup.launch.py robot_id:=pinky1`. 관제 PC에서 `ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/pinky1/cmd_vel -p speed:=0.08 -p turn:=0.5`

### 로봇별 설정 (등록부)

등록부의 로봇 항목에 적으면 `robot_remote`와 `real.launch.py` 원격 기동이 그 로봇의 `robot.launch.py`에 넘깁니다.

```yaml
robots:
  pinky1:
    host: ...
    wheel_radius: 0.02743       # m, 바퀴 반지름
    wheel_separation: 0.0966    # m, 바퀴 간격
    launch_args: {cmd_vel_timeout: "0.3"}
```

- 바퀴 치수(2026-11-26 줄자 1 m 직진 3회 평균): pinky1 0.02743·0.0966, pinky2 0.02735·0.0977, pinky3 0.02737·0.0983. 키가 없으면 명목값 0.027·0.0961입니다. 적용 여부는 기동 로그 `[pinkyN] wheel_radius ... (robot value)`로 확인합니다.
- `cmd_vel_timeout`: `pinky_driver`가 `cmd_vel`이 이 시간 넘게 끊기면 모터를 세웁니다. 기본 0.3 s(2026-11-25부터, 이전 0.5 s). 한 번만 바꿀 때는 `robot_remote pinky1 --map-id test_map_v05 --arg cmd_vel_timeout:=0.5`.

### 서빙 팔 (JetCobot, 실기기 통합 동작은 확인 전)

팔 Pi의 구동부는 원격으로 띄우지 않고 현장에서 직접 실행합니다. 팔 Pi에는 `frybot_interfaces`, `frybot_mobile`만 복사해 빌드합니다.

```bash
# 관제 PC: 팔 Pi에서 칠 명령 한 줄 출력 (팔을 올린 로봇을 --mount 로)
ros2 run frybot_bringup robot_remote jetcobot1 --arm-command --mount pinky1
# 관제 + pinky1 (등록부 arms 의 mount 에 있으면 serving_arm:=real 이 자동으로 붙음)
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v04 robots:=pinky1 serving_robots:=pinky1
# 연결 확인 / 서빙 임무
ros2 action list | grep serving_arm
ros2 service call /fms/submit_task frybot_interfaces/srv/SubmitTask "{task_type: 'SERVE', table_id: 1, menu: 'FRIED'}"
```

- 작업 이름: `REST`는 주행용 접은 자세, `HOME`은 0도 자세(충전소 대기). `serving_arm:=real`인 로봇은 주행 전에 팔을 접고, 자기 충전소에 도착하면 1초 뒤 폅니다.
- `LOAD`·`UNLOAD`는 시험용 좌우 흔들기이며 실제 음식 전달 자세가 아닙니다. 팔 없이 주행만 시험할 때는 `serving_arm`을 비워 띄웁니다.

### 손님 추적 AI 서버 (`frybot_ai`, 실기기 안내 주행 확인 필요)

Pinky 카메라 영상을 관제 PC가 직접 받아 YOLO로 사람을 찾고 `GUEST_TRACK`을 `central_control`(:8100)로 보냅니다. 처음 한 번 `python3 -m venv ~/venv/yolo && ~/venv/yolo/bin/pip install ultralytics`로 가상 환경을 만듭니다.

| 상황 | 명령 |
|---|---|
| Pinky에서 카메라 송신 (배포 뒤) | `ros2 launch frybot_mobile camera_streamer.launch.py` (640×480 15 fps, TCP 8554) |
| 관제 PC에서 손님 추적 (등록부의 모든 로봇) | `ros2 launch frybot_ai guest_tracker.launch.py` |
| 일부 로봇만 / 회전 지정 | `... cameras:=pinky1=<주소>,pinky2=<주소>@180` |
| 관제 없이 화면만 | `... central_url:=none` |

- 확인 화면: http://127.0.0.1:8095 (주황 상자가 손님). 카메라 스트림에는 한 번에 하나만 붙습니다.

### 상태 확인

| 확인할 것 | 명령 |
|---|---|
| 로봇 상태 보고 | `ros2 topic echo /fleet/robot_status --once` |
| Nav2 기동 여부 (`active`면 정상) | `ros2 lifecycle get /pinky1/bt_navigator` |
| 관제 생존 신호 (5 Hz) | `ros2 topic hz /fms/heartbeat` |
| 통행 허가 | `ros2 topic echo /fms/traffic_grant` |
| 라이다 주기 | `ros2 topic hz /pinky1/scan` |
| 배터리 | `ros2 topic echo /pinky1/battery/percent --once` |
| 로봇의 런치 로그 (Pinky 안에서) | `tail -f ~/.frybot/robot_launch.log` |

## 4. 관제 화면과 이동 명령

| 화면 | 주소 |
|---|---|
| 관리자 (통합 관제, 테이블·주문, 알람·이력, 설정) | http://localhost:8080/admin |
| 입구 접수 | http://localhost:8080/reception |
| 테이블 주문 | http://localhost:8080/table?id=1 |
| 손님 시뮬레이터 (가상 매장 시뮬에서만) | http://localhost:8090 |

접수와 테이블 주문은 가상 매장(`proto`)에서만 동작합니다. 이동 명령은 관리자 화면의 운영 지도에서 로봇과 목적 노드를 고르고 **이동 명령**을 누릅니다. 터미널에서는 다음과 같습니다(관리자 경로는 I/F v0.3 기준 `/api/admin/operations`, 예전 `/api/admin`은 받지 않음).

```bash
# pinky1을 노드 B5로
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"MOVE_TO_VERTEX","target":"pinky1","arg":"B5"}' http://localhost:8080/api/admin/operations
# pinky2 비상 정지 / 재개
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"ESTOP","target":"pinky2"}' http://localhost:8080/api/admin/operations
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"RESUME","target":"pinky2"}' http://localhost:8080/api/admin/operations
# 관제 상태 / 지도 목록 / 최근 이벤트
curl -s http://localhost:8080/api/state
curl -s http://localhost:8080/api/maps
curl -s http://localhost:8080/api/events
```

실기기에서 관리자 명령은 기본으로 관제 PC에서만 받습니다. 다른 기기에서 보내려면 런치에 `admin_token:=<값>`을 주고 요청에 `X-Admin-Token` 헤더를 붙입니다.

## 5. 결과 확인

실행 기록은 런치를 띄운 폴더의 `runs/<run_id>/events.csv`에 쌓입니다.

| 하려는 것 | 명령 |
|---|---|
| 최근 실행 폴더 | `ls -t runs \| head -3` |
| 지표 요약 | `ros2 run frybot_control analyze_run runs/<run_id>` |
| 실기기 기록을 모의 실행과 비교 | `ros2 run frybot_control replay_run runs/<run_id> -v` |
| 양보가 일어나는 명령 조합 찾기 | `ros2 run frybot_control replay_run --find-yield --map-id test_map_v001` |
| 양보·복귀·재시도 이벤트만 보기 | `grep -E "YIELD\|RETREAT\|PLAN_WAIT\|REJOIN\|ROUTE_RETRY" runs/<run_id>/events.csv` |

`analyze_run`에는 폴더 경로를 반드시 넘깁니다. `--help`는 지원하지 않습니다.

## 6. 알고리즘 비교 (ROS 실행 없이 계산만)

| 하려는 것 | 명령 |
|---|---|
| 한 시나리오의 모든 조합 | `ros2 run frybot_control fleet_bench --scenario rush` |
| 기본 조합만, 통과 판정까지 | `ros2 run frybot_control fleet_bench --scenario rush --schedulers min_cost_eta_rh --planners sipp --check` |
| 조합을 골라 3회 평균, CSV 저장 | `ros2 run frybot_control fleet_bench --scenario bottleneck --seeds 3 --schedulers min_cost min_cost_eta_rh --planners sipp ccbs --csv raw.csv --csv-mean mean.csv` |
| 실측 지도 이동 명령 비교 | `ros2 run frybot_control fleet_bench --scenario moves --map-id test_map_v05 --robots 2 --seeds 30 --schedulers min_cost_eta_rh --planners sipp independent_astar --jobs 8` |

- 시나리오는 `normal`, `rush`, `bottleneck`, `moves`(실측 지도)입니다. `--check`는 못 넘으면 종료 코드 1을 돌려줍니다.
- 관제 로직이나 스케줄러·플래너를 고쳤으면 `fleet_bench --scenario rush` 결과를 고치기 전과 비교합니다.

## 7. 지도

| 하려는 것 | 명령 |
|---|---|
| 가상 매장 지도 파일 다시 만들기 (`layout.py`를 고친 뒤) | `ros2 run frybot_control export_map --proto` |
| 지도를 고친 뒤 PC에 반영 | `colcon build --symlink-install --packages-select frybot_control frybot_web` |
| 지도를 로봇에 반영 | 3장의 배포 명령 |

- 지도 폴더는 `frybot/frybot_control/frybot_control/maps/<map_id>/`입니다(`proto`, `test_map_v001`, `test_map_v002`, `test_map_v03`, `test_map_v04`, `test_map_v05`, `test_map_v06`).
- `roadmap.json`의 `"dock_backwards"`: 그 지도의 도크에 뒤로 들어갈지. 키가 없으면 실측 지도는 `true`, `test_map_v04`·`test_map_v05`는 `false`(전진). 바꾼 뒤에는 PC 빌드와 로봇 배포가 필요합니다.

## 8. 하지 말 것

| 하지 말 것 | 이유 |
|---|---|
| `map_id` 없이 `real.launch.py` | 런치가 오류로 멈춤. `proto`도 받지 않음 |
| Pinky가 켜진 상태에서 `net:=lan`으로 시뮬레이션 | 같은 도메인에서 `/pinky1..3` 이름이 겹쳐 실제 로봇이 시뮬 관제의 경로를 주행할 수 있음 |
| 같은 PC에서 시뮬과 실기기를 함께 띄우기 | 같은 이유 |
| 로봇 프로그램이 도는 중에 `--deploy` | 실행 중인 코드가 바뀜 |
| `robots.yaml`을 저장소에 올리기 | SSH 비밀번호가 들어 있음 |
| `export_map --help`, `analyze_run --help` | 도움말이 아니라 `--help`를 경로로 받아들임 |
