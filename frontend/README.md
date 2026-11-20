# OneTeam 스마트 레스토랑 프론트엔드

`design/gui/` 시안을 React + Vite + TypeScript로 구현한 앱입니다. 기기별 화면은 주소로 나뉩니다.

| 주소 | 화면 | 상태 |
|---|---|---|
| `/kiosk` | 입구 키오스크 K1~K4 | 구현 |
| `/table/:번호` | 테이블 태블릿 T1~T5 (예: `/table/3`) | 구현 |
| `/admin` | 관리자 PC A1 통합 관제 | 구현 |
| `/admin/tables` | 관리자 PC A2 테이블 · 주문 · 조리 | 구현 |
| `/admin/alarms` | 관리자 PC A3 알람 · 이력 (Replay) | 구현 |

## 실행

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (같은 와이파이의 태블릿에서도 접속 가능)
npm test           # 흐름 테스트
npm run build      # dist/ 에 배포용 파일
```

기본 주소는 **진짜 백엔드 서버**를 씁니다. 같은 주소 앞에 **`/mock`** 을 붙이면 서버 없이 **목업(가짜) 데이터**로 봅니다.
목업 화면에는 왼쪽 아래에 "목업 데이터" 표시가 붙습니다.

| 진짜 서버 | 목업 데이터 |
|---|---|
| `/` (화면 목록) | `/mock` |
| `/kiosk` | `/mock/kiosk`, `/mock/kiosk?robot=busy` (로봇 대기 흐름) |
| `/table/3` | `/mock/table/3` |
| `/admin`, `/admin/tables`, `/admin/alarms` | `/mock/admin`, `/mock/admin/tables`, `/mock/admin/alarms` |

서버가 꺼져 있으면 진짜 서버 화면은 매장 구성만 보이고 상태는 "연결 안 됨"으로 표시됩니다.

첫 화면(`/`) 위쪽에서 **진짜 서버 / 목업 데이터** 를 고르면 아래 화면 목록이 그쪽 주소로 바뀝니다 (화면마다 버튼 하나).
백엔드 개발자는 **`/check`(백엔드 연결 점검)** 에서 붙일 순서와 지금 된 것·안 된 것을 볼 수 있습니다.


- `/mock/kiosk`: 로봇이 바로 오는 흐름 K1 → K2 → K4
- `/mock/kiosk?robot=busy`: 로봇이 모두 안내 중인 흐름 K1 → K2 → K3 → K4
- `/mock/table/3`: 메뉴 담기(T1) → 주문 확인(T2) → 진행 상태(T3) → 음식 도착(T4) → T3.
  음식을 다 받은 뒤 T3의 "이용 종료"를 누르면 확인창(T5). 가짜 API는 1.5초마다 한 단계씩 진행합니다.
  가짜 API에서는 태블릿을 열면 그 테이블에 손님이 앉은 것으로 만들어 줍니다.
- `/mock/admin`: 가짜 매장을 화면을 열기 전 25분 동안 미리 돌려 둡니다(손님 도착 → 안내 → 주문 → 조리 → 서빙 → 이용 종료 → 정리).
  열기 2분쯤 전에 그리퍼 오류(E-ARM-021)가 하나 나 있어서, A3에서 재시도 · 작업 취소를 해 볼 수 있습니다.
  관리자 가짜 매장은 키오스크·태블릿의 가짜 API와 따로 돕니다(같은 탭에서 서로 연결되지 않음).

## 구조

```
src/
  api/                 프론트 ↔ Web Service 경계
    schema.gen.ts      api/openapi.yaml 에서 자동 생성한 타입 (npm run gen:api, 직접 고치지 않음)
    contract.ts        생성된 타입을 화면에서 쓰는 이름으로 + 손님 화면 API 인터페이스
    schemaCheck.ts     openapi.yaml 로 응답 모양 검사 (계약 테스트, /check)
    storeLayout.ts     매장 배치 (맵 구성도 2026-11-13, frybot layout.py와 같은 좌표)
    mockApi.ts         서버 없이 매장을 흉내 내는 가짜 Web Service
    httpApi.ts         실제 Web Service(FastAPI) 연결 (VITE_API_MODE=http)
    adminContract.ts   관리자 화면 타입(생성된 것) + 관리자 API 인터페이스
    adminMock.ts       관리자용 가짜 매장 시뮬레이션 (AMR 3대 pinky1~3, 로봇팔 2대, 길 찾기)
    adminHttp.ts       관리자 화면 ↔ 실제 Web Service
  components/
    Robot.tsx          로봇 캐릭터 SVG (wave · peek · wait · guide · confirm · cook · serve)
    Stage.tsx          932×572 시안을 기기 화면에 맞게 비율 유지로 확대
    StoreMap.tsx       K2 매장 배치도와 입구→테이블 안내 경로
    customer.module.css  고객 화면(K·T) 공통 스타일
  kiosk/               K1~K4 화면과 화면 전환 흐름
  table/               T1~T5 화면과 화면 전환 흐름
  admin/               A1~A3 화면 (StoreMap3D: 맵 구성도를 CSS 3D로 그린 매장 지도)
```

## 백엔드 연결 (FastAPI + rclpy)

**계약 우선(contract-first)** 으로 갑니다. 화면과 서버가 주고받는 모양의 기준은 저장소의 **[`api/openapi.yaml`](../api/openapi.yaml)** 하나입니다
(Confluence **1) FryBot I/F 목록**·**4) Logical Data Model**을 옮긴 것, 문서에 없던 것은 `[제안]`).

1. 모양을 바꿀 때는 `api/openapi.yaml` 을 먼저 고칩니다 → `npm run lint:api` 로 문법 확인
2. 프론트: `npm run gen:api` → `src/api/schema.gen.ts` 가 다시 만들어지고, 타입이 안 맞는 화면 코드는 `npm run build` 에서 바로 드러납니다
3. 목업이 계약을 지키는지: `npm test` (`src/api/contract.test.ts` — 목업 응답을 openapi.yaml 로 검사)
4. 백엔드가 계약을 지키는지: 개발 서버의 **`/check`** 화면, 또는 아래 "백엔드 개발자용"
5. 보기 좋은 문서로 보기: `npm run docs:api` → http://localhost:8090

`/mock` 이 없는 주소의 화면은 `/api/*` 요청과 WebSocket(`/api/ws`)을 백엔드로 넘깁니다.
백엔드 주소는 `frontend/.env` 의 `BACKEND_URL` 한 줄 (`.env.example` 을 복사해서 만들기, 없으면 `http://localhost:8000`).
주소를 바꾼 뒤에는 `npm run dev` 를 껐다 켜야 합니다.
목업(`/mock`)과 `/check` 는 개발 서버에서만 있고, 배포 파일(`npm run build`)에는 들어가지 않습니다.

### 백엔드 개발자용

- 서버는 `/api` 아래에 엽니다 (FastAPI: `app.include_router(router, prefix="/api")`).
- Pydantic 모델은 계약에서 만들 수 있습니다:
  `pip install datamodel-code-generator` → `datamodel-codegen --input api/openapi.yaml --input-file-type openapi --output-model-type pydantic_v2.BaseModel --output models.py`
- FastAPI 를 켜면 `http://localhost:8000/docs` 에서 주소마다 직접 요청을 보내 시험할 수 있습니다 (화면 없이).
- 계약 테스트(서버 응답이 openapi.yaml 과 같은지 자동 검사):
  `pip install schemathesis` → `st run api/openapi.yaml --url http://localhost:8000/api --include-method GET`
  (POST 는 손님 접수·주문이 실제로 생겨 로봇이 움직일 수 있으니 시뮬레이터에서만 돌리세요)
- 붙이는 순서와 지금 상태는 개발 서버의 `/check` 화면 (서버 켜짐 → 메뉴 → 테이블 → 접수 → 방문 상태 → 실시간 알림 → 주문 → 이용 종료 → 관리자).

요약 표 (자세한 모양은 openapi.yaml):

| I/F | 경로 | 화면 |
|---|---|---|
| WEB-01 | `POST /visits` `{party_size, request_key}` → `{visit_id, status: ASSIGNED\|WAITING, table_id, queue_no}` | K1 |
| WEB-02 | `GET /visits/{visit_id}/status` → 방문 스냅샷 (안내 진행 `guide`, 주문 목록, `can_end`, `version`) | K2~K4, T3 |
| WEB-03 | `GET /menu?table_id=` → `[{menu_id, name, price\|null, is_available}]` | T1 |
| WEB-04 | `POST /orders` `{visit_id, table_id, items:[{menu_id, qty}], request_key}` | T2 |
| WEB-06 | `POST /visits/{visit_id}/end` `{request_key}` → `{result: ACCEPTED\|PENDING, collect_required}` | T5 |
| - | `GET /tables` → `[{table_id, code, seats, status, visit_id}]` | 태블릿이 현재 방문을 찾음 |
| 상태 변경 구독 | `WS /ws` — 보냄 `{type:"subscribe", topics:[{visit_id}\|{table_id}]}`, 받음 `{type:"visit"\|"table", version, data}` | 전체 |
| (목록에 없음) | `POST /staff-calls` `{source, table_id}` | 직원 호출 |
| WEB-07 | `GET /admin/overview` → `{robots, tables, orders, tasks, alarms, ros_connected, version}` | A1~A3 |
| WEB-08 | `POST /admin/operations` `{kind, target_id, params?, request_key}` → `{operation_id, result: ACCEPTED\|CONFLICT\|PENDING, reason}` | A1~A3 조작 |
| WEB-09 | `GET /admin/operations/{operation_id}` → `{status: PENDING\|SUCCEEDED\|FAILED\|UNKNOWN, message}` | 조작 결과 |
| 상태 변경 구독 | `WS /ws` 보냄 `{type:"subscribe", topics:[{admin:true}]}`, 받음 `{type:"admin", version, data: 현황}` (최대 2 Hz) | A1~A3 |
| (목록에 없음) | `GET /admin/events?from&to` → event_log 행, `GET /admin/replay?from&to` → 초당 로봇 위치 | A3 이력 · Replay |

관리자 조작 `kind`: `PAUSE` · `RESUME` · `REASSIGN` · `E_STOP` (로봇), `SET_TABLE_STATUS` (테이블, `params.status`),
`INCIDENT_RETRY` · `INCIDENT_STOP` (오류 처리 = incident.admin_choice RETRY/STOP), `ACK_ALARM` (알람 읽음).
화면은 WEB-08이 `ACCEPTED`면 WEB-09로 결과를 확인하고, 결과를 모르면 다시 누를 때 같은 요청 키를 씁니다.
로봇 위치는 ROS map 좌표(m, y 위쪽) 그대로 받고 화면에서 맵 구성도(cm)로 바꿉니다.

- 요청 키: 버튼을 누를 때마다 새로 만들고, 결과를 모를 때(503 `RESULT_UNCONFIRMED`·네트워크 끊김) 다시 누르면 **같은 키**로 보냅니다.
- 구독: 연결·재연결 때 스냅샷을 다시 조회해 누락을 복원하고, `version`이 같거나 작은 메시지는 버립니다.
- 상태 이름은 Logical Data Model 그대로입니다. 주문 `ORDERED → COOKING → READY → SERVING → ARRIVED → COMPLETED`, 방문 `WAITING/ASSIGNED/IN_USE/END_OF_USE`, 테이블 `AVAILABLE/ASSIGNED/IN_USE/CLEANING`.

## 시안에 없어서 정한 것

- K1: 인원을 고르기 전에는 주 버튼을 끔. 빈 자리가 없으면 안내 문구
- 직원 호출을 누르면 위쪽에 알림
- T1: 이미 주문이 있으면 "주문 현황" 버튼으로 T3로 돌아갈 수 있음
- T3: "이용 종료" 버튼(T5 확인창을 여는 곳)을 "추가 주문" 옆에 둠
- 이용 종료 뒤 "이용해 주셔서 고마워요" 화면. 직원이 정리를 마치면(서버가 세션을 다시 열면) T1로
- 메뉴 가격은 가짜 API의 예시 값 (치킨 18,000원, 볶음밥 9,000원)
- 테이블 이름은 맵 구성도처럼 "5번 테이블" (시안의 "T5 테이블" 대신)
- 테이블 배정 순서(가짜 API): 인원에 딱 맞는 좌석, 같으면 입구에서 가까운 순 (5 → 6 → 1 → 2, 4인석 4 → 3)
- 빈 테이블이 없으면(WAITING) K1에 대기 번호 안내 — 시안에 대기 화면이 없음
- 받지 않은 음식이 있으면 "이용 종료" 대신 안내 문구 (`can_end`)
- 가격이 없으면(`price: null`) 금액 표시를 보류
- 관리자 지도: 시안의 "중앙 섬 배치" 대신 맵 구성도(2026-11-13) 배치. 충전대 · 받는 곳 · 비켜 서는 곳 · 대기 칸은 frybot `layout.py` 값
- 로봇 이름: `pinky1~3` → AMR-1~3, `cook_arm_a/b` → 튀김 로봇팔 ARM-1 / 웍 로봇팔 ARM-2
- A1 비상 정지는 확인창을 한 번 거침. 비상 정지 중인 로봇은 A3에서 재시도 · 작업 취소
- A1 "일시정지"는 지도 화면만 멈춤(로봇은 계속 움직임). 로봇을 멈추는 건 오른쪽 "일시 중단"
- A2 "상태 변경"은 정리 대기 / 이용 가능 두 가지만. 손님 배정은 키오스크에서만
- A3 알람을 고르면 읽음 처리. 조회 결과 목록을 누르면 그 시각으로 Replay 이동

## 팀과 확인할 것

- K2·K3에서 "처음으로"를 누를 때 방문을 취소하는 인터페이스가 없음 (지금은 화면만 처음으로 돌아감. State Diagram에도 visit CANCELED 없음)
- 직원 호출 인터페이스가 I/F 목록에 없음 (`POST /staff-calls`로 제안)
- 테이블 태블릿이 자기 테이블의 현재 방문을 찾는 방법 (`GET /tables`의 `visit_id`로 제안)
- 도착 예정 시각(ETA)과 T4 전달 단계(`delivery_step`)를 Web Service가 줄 수 있는지
- WEB-07 현황 응답의 필드 구성, WEB-08 조작 종류(`kind`) 이름 — 문서에 아직 없음 (`adminContract.ts`로 제안)
- 운영 이력 조회 · Replay 인터페이스가 I/F 목록에 없음 (`GET /admin/events`, `GET /admin/replay`로 제안)
- 알람 = incident + 경고·정보. 경고·정보(W-GUIDE-02, I-BAT-01 등)를 저장할 테이블이 Logical Data Model에 없음
- 로봇팔의 일시 중단 상태가 robot.state에 없음 (A1에서 로봇팔은 비상 정지만)
