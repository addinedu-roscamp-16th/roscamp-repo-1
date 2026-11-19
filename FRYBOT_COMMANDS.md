# FryBot 실행 명령

`frybot/` 폴더의 패키지를 받아서 빌드하고 실행하는 명령입니다. 전체 구조와 인터페이스는 [frybot/README.md](frybot/README.md)를 참고합니다.

- 작성: 2026-11-19
- 환경: Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, Nav2 Jazzy
- 확인(2026-11-19): 이 저장소의 `frybot/`만으로 새 작업 공간에서 빌드(8개 패키지)와 `fleet_bench --scenario rush` 실행을 확인했습니다. 시뮬·실기기 런치는 이 문서를 쓰면서 다시 실행하지 않았습니다.
- `<run_id>`처럼 꺾쇠로 적은 부분은 실제 값으로 바꿉니다.
- 원본 작업 공간의 `docs/`와 `scripts/`(전체 종료 스크립트, 카메라 녹화 등)는 이 저장소에 없습니다. `frybot/README.md`의 `docs/...`, `scripts/...` 링크는 열리지 않습니다.

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
| 최신 코드 받기 | `cd ~/frybot_ws/src/roscamp-repo-1 && git pull` 후 다시 빌드 |
| 터미널을 열 때마다 | `cd ~/frybot_ws && source install/setup.bash` |

- 외부 저장소(`pinky_pro`, `mycobot_ros2`)는 빌드와 실행에 필요하지 않습니다. 쓰는 모델 파일은 `frybot_description`에 들어 있습니다.
- 저장소에 다른 팀원의 패키지가 함께 있으면 `--packages-up-to frybot_bringup`을 꼭 붙여 FryBot 패키지만 빌드합니다.

## 2. 시뮬레이션

시뮬은 전용 도메인 74에서 돕니다(`net:=sim`이 기본). 켜져 있는 실제 Pinky(도메인 73)와 서로 보이지 않습니다. 시뮬에 `ros2 topic` 같은 명령을 쓰는 터미널에서는 먼저 `export ROS_DOMAIN_ID=74`를 실행합니다. 시나리오 실행기와 웹 화면은 HTTP만 써서 필요 없습니다.

### 가상 매장 (접수부터 서빙·회수까지)

```bash
# 터미널 1: 경량 시뮬 + RViz
ros2 launch frybot_bringup sim.launch.py
# 터미널 2: 자동 시나리오 (demo | normal | rush | single)
ros2 run frybot_sim scenario --scenario demo
```

### 실측 지도 (노드 간 이동만)

```bash
ros2 launch frybot_bringup sim.launch.py map_id:=test_map_v003
```

- 지도: `test_map_v03`, `test_map_v04`
- 매장·손님·조리 팔·AI 서버는 뜨지 않습니다. 이동 명령은 4장을 봅니다.

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
| `cook_time_scale` | `20` | 조리 시간 축소 |

전체 인자는 `frybot/README.md`의 "런치 인자" 표에 있습니다.

## 3. 실기기 (Pinky)

실기기는 도메인 73을 씁니다. 로봇 주소와 계정은 저장소 밖의 `~/.config/frybot/robots.yaml`에 등록합니다. 비밀번호가 들어가므로 저장소에 올리지 않습니다.

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
| 실제로 실행될 내용만 출력 | 위 명령에 `--dry-run`을 붙임 |
| 로봇에 남은 프로그램 정지 | `ros2 run frybot_bringup robot_remote --all --stop` |

코드나 지도를 고쳤으면 빌드 → 배포 → 점검 순서로 합니다. 로봇 프로그램이 도는 중에는 배포하지 않습니다.

### 기동

```bash
# 로봇 3대를 W1·W2·W3에 놓고 -x 방향(180도)을 향하게 둔 경우
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 poses:=pinky1:W1:180,pinky2:W2:180,pinky3:W3:180
# 한 대만
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 robots:=pinky1 poses:=pinky1:W1:180
# 자동 홈 이동과 RViz 없이 (상태만 관찰)
ros2 launch frybot_bringup real.launch.py map_id:=test_map_v001 poses:=pinky1:W1:180,pinky2:W2:180,pinky3:W3:180 auto_home:=false rviz:=false
# RViz만 따로
ros2 launch frybot_bringup fleet_rviz.launch.py robots:=pinky1,pinky2,pinky3
```

- `map_id`는 필수이고 실측 지도여야 합니다. PC와 Pinky가 같은 `map_id`를 써야 합니다.
- `poses`는 `로봇:노드[:방향(도)]`이며 로봇이 실제로 서 있는 자리에 맞춥니다. 0도는 +x, 180도는 -x입니다. 생략하면 RViz의 **2D Pose Estimate**로 지정합니다.
- 기본값 `auto_home:=true`에서는 위치가 잡힌 로봇이 기동 직후 자기 출발 노드로 움직입니다.
- 종료는 런치 터미널에서 Ctrl-C입니다. 로봇 쪽도 함께 멈춥니다. 로봇에 프로그램이 남았으면 `robot_remote --all --stop`을 씁니다.
- Pinky 안에서 직접 띄울 때: `ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 map_id:=test_map_v001`

### 상태 확인

| 확인할 것 | 명령 |
|---|---|
| 로봇 상태 보고 | `ros2 topic echo /fleet/robot_status --once` |
| Nav2 기동 여부 (`active`면 정상) | `ros2 lifecycle get /pinky1/bt_navigator` |
| 관제 생존 신호 (5 Hz) | `ros2 topic hz /fms/heartbeat` |
| 라이다 주기 | `ros2 topic hz /pinky1/scan` |
| 배터리 | `ros2 topic echo /pinky1/battery/percent --once` |

## 4. 관제 화면과 이동 명령

| 화면 | 주소 |
|---|---|
| 관리자 (통합 관제, 테이블·주문, 알람·이력, 설정) | http://localhost:8080/admin |
| 입구 접수 | http://localhost:8080/reception |
| 테이블 주문 | http://localhost:8080/table?id=1 |
| 손님 시뮬레이터 (가상 매장 시뮬에서만) | http://localhost:8090 |

이동 명령은 관리자 화면의 운영 지도에서 로봇과 목적 노드를 고르고 **이동 명령**을 누릅니다. 터미널에서는 다음과 같습니다.

```bash
# pinky1을 노드 B5로
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"MOVE_TO_VERTEX","target":"pinky1","arg":"B5"}' http://localhost:8080/api/admin
# pinky2 비상 정지 / 재개
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"ESTOP","target":"pinky2"}' http://localhost:8080/api/admin
curl -s -X POST -H 'Content-Type: application/json' -d '{"command":"RESUME","target":"pinky2"}' http://localhost:8080/api/admin
# 관제 상태 / 최근 이벤트
curl -s http://localhost:8080/api/state
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

`analyze_run`에는 폴더 경로를 반드시 넘깁니다. `--help`는 지원하지 않습니다.

## 6. 알고리즘 비교 (ROS 실행 없이 계산만)

| 하려는 것 | 명령 |
|---|---|
| 한 시나리오의 모든 조합 | `ros2 run frybot_control fleet_bench --scenario rush` |
| 기본 조합만 | `ros2 run frybot_control fleet_bench --scenario rush --schedulers min_cost_eta_rh --planners sipp` |
| 조합을 골라 3회 평균, CSV 저장 | `ros2 run frybot_control fleet_bench --scenario bottleneck --seeds 3 --schedulers min_cost min_cost_eta_rh --planners sipp ccbs --csv raw.csv --csv-mean mean.csv` |
| 실측 지도 이동 명령 비교 | `ros2 run frybot_control fleet_bench --scenario moves --map-id test_map_v001 --robots 3 --seeds 30 --schedulers min_cost_eta_rh --planners sipp independent_astar --jobs 8` |
| 통과 판정까지 | 위 명령에 `--check`를 붙임 (못 넘으면 종료 코드 1) |

시나리오는 `normal`, `rush`, `bottleneck`, `moves`(실측 지도)입니다.

## 7. 지도

| 하려는 것 | 명령 |
|---|---|
| 가상 매장 지도 파일 다시 만들기 (`layout.py`를 고친 뒤) | `ros2 run frybot_control export_map --proto` |
| 지도를 고친 뒤 PC에 반영 | `colcon build --symlink-install --packages-select frybot_control frybot_web` |
| 지도를 로봇에 반영 | 3장의 배포 명령 |

지도 폴더는 `frybot/frybot_control/frybot_control/maps/<map_id>/`입니다.

## 8. 하지 말 것

| 하지 말 것 | 이유 |
|---|---|
| `map_id` 없이 `real.launch.py` | 런치가 오류로 멈춤. `proto`도 받지 않음 |
| Pinky가 켜진 상태에서 `net:=lan`으로 시뮬레이션 | 같은 도메인에서 `/pinky1..3` 이름이 겹쳐 실제 로봇이 시뮬 관제의 경로를 주행할 수 있음 |
| 같은 PC에서 시뮬과 실기기를 함께 띄우기 | 같은 이유 |
| 로봇 프로그램이 도는 중에 `--deploy` | 실행 중인 코드가 바뀜 |
| `robots.yaml`을 저장소에 올리기 | SSH 비밀번호가 들어 있음 |
