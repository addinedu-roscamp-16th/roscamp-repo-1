# OneTeam 스마트 레스토랑 프론트엔드

`design/gui/` 시안을 React + Vite + TypeScript로 구현한 앱입니다. 기기별 화면은 주소로 나뉩니다.

| 주소 | 화면 | 상태 |
|---|---|---|
| `/kiosk` | 입구 키오스크 K1~K4 | 구현 |
| `/table/:번호` | 테이블 태블릿 T1~T5 (예: `/table/3`) | 구현 |
| `/admin` | 관리자 PC A1~A3 | 준비 중 |

## 실행

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (같은 와이파이의 태블릿에서도 접속 가능)
npm test           # 흐름 테스트
npm run build      # dist/ 에 배포용 파일
```

지금은 백엔드 없이 **가짜 API(mock)** 로 동작합니다.

- `/kiosk`: 로봇이 바로 오는 흐름 K1 → K2 → K4
- `/kiosk?robot=busy`: 로봇이 모두 안내 중인 흐름 K1 → K2 → K3 → K4
- `/table/3`: 메뉴 담기(T1) → 주문 확인(T2) → 진행 상태(T3) → 음식 도착(T4) → T3.
  음식을 다 받은 뒤 T3의 "이용 종료"를 누르면 확인창(T5). 가짜 API는 1.5초마다 한 단계씩 진행합니다.
  가짜 API에서는 태블릿을 열면 그 테이블에 손님이 앉은 것으로 만들어 줍니다.

## 구조

```
src/
  api/                 프론트 ↔ Web Service 경계
    contract.ts        주고받는 데이터 모양 (Confluence I/F 목록·Logical Data Model 기준)
    storeLayout.ts     매장 배치 (맵 구성도 2026-11-13, frybot layout.py와 같은 좌표)
    mockApi.ts         서버 없이 매장을 흉내 내는 가짜 Web Service
    httpApi.ts         실제 Web Service(FastAPI) 연결 (VITE_API_MODE=http)
  components/
    Robot.tsx          로봇 캐릭터 SVG (wave · peek · wait · guide · confirm · cook · serve)
    Stage.tsx          932×572 시안을 기기 화면에 맞게 비율 유지로 확대
    StoreMap.tsx       K2 매장 배치도와 입구→테이블 안내 경로
    customer.module.css  고객 화면(K·T) 공통 스타일
  kiosk/               K1~K4 화면과 화면 전환 흐름
  table/               T1~T5 화면과 화면 전환 흐름
```

## 백엔드 연결 (FastAPI + rclpy)

Confluence **1) FryBot I/F 목록**(2026-11-20 설계 검토안)을 따릅니다.
`VITE_API_MODE=http npm run dev` 로 실행하면 `/api/*` 요청이 `http://localhost:8000` 으로 넘어갑니다.
JSON 필드는 `src/api/contract.ts`에 있습니다. 문서가 "확인 필요"로 남긴 형식은 `[제안]`으로 표시했습니다.

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

## 팀과 확인할 것

- K2·K3에서 "처음으로"를 누를 때 방문을 취소하는 인터페이스가 없음 (지금은 화면만 처음으로 돌아감. State Diagram에도 visit CANCELED 없음)
- 직원 호출 인터페이스가 I/F 목록에 없음 (`POST /staff-calls`로 제안)
- 테이블 태블릿이 자기 테이블의 현재 방문을 찾는 방법 (`GET /tables`의 `visit_id`로 제안)
- 도착 예정 시각(ETA)과 T4 전달 단계(`delivery_step`)를 Web Service가 줄 수 있는지
