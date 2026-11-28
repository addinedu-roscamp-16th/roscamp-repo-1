# JetCobot 동작 플레이어

로봇팔(JetCobot) 동작을 팀이 같이 관리하고 재생하는 웹 도구다. 서버 노트북 한 대에서 실행하고, 팀원은 같은 와이파이에서 브라우저로 접속한다.

| 탭 | 하는 일 |
|---|---|
| 조작 | 기본자세·정면 대기·서보 고정/풀기, 관절 각도·좌표 이동, 그리퍼, 자세 기록, 자세 → 동작 저장 |
| 애니메이션 | 동작 목록·관절 그래프, 브라우저 3D 미리보기, RViz 재생(누른 사람 컴퓨터), 실제 로봇 재생, 손으로 따기, 업로드·삭제 |

동작 목록은 [MOTIONS.md](MOTIONS.md) 에 자동으로 정리된다.

## 실행 (서버 노트북)

```bash
./동작플레이어.sh          # 처음 한 번: 우클릭 → 프로그램으로 실행. 바탕화면 아이콘이 생김
```

- 주소: `http://<서버 IP>:8765`. 팀 접속 코드는 `player/access_code.txt` (처음 실행 때 생성, 저장소에 안 올림)
- 실제 로봇은 서버가 SSH 로 접속해 `robot_link/agent.py` 를 실행한다. 로봇에 설치할 것은 없다.
- 팀 공용 키 `jetcobot-team.key` 를 다운로드 폴더에 두면 자동으로 인식한다 (저장소에 없음, 관리자에게 받기).
- 로봇 목록은 `robot_link/team/robots.json` (실기기 접속 정보라 저장소에 안 올림). 웹 화면의 `＋ 로봇 등록` 으로 추가한다. 형식은 `robots.example.json`.

## RViz 를 내 컴퓨터에서 (팀원)

애니메이션 탭의 "처음이면: 내 컴퓨터에 RViz 재생기 설치" 를 한 번 실행한다. ROS 2 Jazzy 가 필요하다. 그 뒤로는 `▶ RViz (내 컴퓨터)` 버튼이 그 컴퓨터에 RViz 를 띄운다. ROS 가 없으면 브라우저 3D 미리보기를 쓴다.

## 동작 파일 형식

`motions/*.json` = ROS 2 `trajectory_msgs/JointTrajectory` 구조 (`joint_names`, `points[].positions` 라디안, `points[].time_from_start`) + 정보(`name`, `robot`, `made_by`, `status`, `scene`, `mount`, `play_hint`).
관절 이름 순서는 `joint2_to_joint1` … `joint6output_to_joint6` (mycobot_280 URDF).

## 폴더

| 경로 | 내용 |
|---|---|
| `player/` | 웹 서버(`server.py`, 표준 라이브러리), 화면(`index.html`), 3D 뷰어(`viewer3d.js`, three.js 0.170 은 `vendor/`), RViz 재생기 설치 파일, 로봇 등록 |
| `motions/`, `graphs/` | 동작 파일과 관절 그래프 |
| `scenes/` | RViz·3D 용 맵 (지금은 `kitchen_table_wok_v2`: 로봇2 웍 공구) |
| `robot/` | 맵 없이 볼 때의 로봇 + 그리퍼 모델 |
| `robot_link/` | 로봇 접속 (`agent.py`, `launch/rssh.sh`, IP 가 바뀌면 MAC 으로 다시 찾는 `find_robot.py`) |
| `tools/` | `play_rviz.py`, `motion_lib.py`(주피터용), `export_scene.py`·`export_from_tester.py`(테스트 도구에서 맵·동작 내보내기), `fix_stl_normals.py` |
| `웍질_재생.ipynb` | 주피터에서 코드로 재생·녹화 |

## 서버 자동 실행 (선택)

`~/.config/systemd/user/motion-player.service` 에 `ExecStart=/usr/bin/python3 player/server.py --no-browser`, `WorkingDirectory=<이 폴더>` 로 두고 `systemctl --user enable --now motion-player`.
