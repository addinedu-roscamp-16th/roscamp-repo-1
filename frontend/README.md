# OneTeam 스마트 레스토랑 프론트엔드

`design/gui/` 시안을 React + Vite + TypeScript로 구현한 앱입니다. 기기별 화면은 주소로 나뉩니다.

| 주소 | 화면 | 상태 |
|---|---|---|
| `/kiosk` | 입구 키오스크 K1~K4 | 구현 |
| `/table/:tableId` | 테이블 태블릿 T1~T5 (예: `/table/T3`) | 구현 |
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
- `/table/T3`: 메뉴 담기(T1) → 주문 확인(T2) → 진행 상태(T3) → 음식 도착(T4) → T3.
  T3의 "이용 종료"를 누르면 확인창(T5). 가짜 API는 1.5초마다 한 단계씩 진행합니다.

## 구조

```
src/
  api/                 프론트 ↔ 백엔드 경계
    types.ts           주고받는 데이터 모양 (백엔드 계약)
    mockKioskApi.ts    서버 없이 흐름을 흉내 내는 가짜 API
    httpKioskApi.ts    FastAPI 백엔드용 (VITE_API_MODE=http)
    tableTypes.ts      테이블 태블릿 데이터 모양
    mockTableApi.ts    주문 → 조리 → 서빙 → 전달을 흉내 내는 가짜 API
    httpTableApi.ts    테이블 태블릿용 백엔드 호출
  components/
    Robot.tsx          로봇 캐릭터 SVG (wave · peek · wait · guide · confirm · cook · serve)
    Stage.tsx          932×572 시안을 기기 화면에 맞게 비율 유지로 확대
    StoreMap.tsx       K2 매장 배치도와 입구→테이블 경로
    customer.module.css  고객 화면(K·T) 공통 스타일
  kiosk/               K1~K4 화면과 화면 전환 흐름
  table/               T1~T5 화면과 화면 전환 흐름
```

## 백엔드 연결 (예정: FastAPI + rclpy)

`VITE_API_MODE=http npm run dev` 로 실행하면 `/api` 요청이 `http://localhost:8000` 으로 넘어갑니다.
백엔드가 맞춰야 할 엔드포인트는 `src/api/httpKioskApi.ts` 위쪽 주석에 있습니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/kiosk/assignments` | `{partySize}` → 테이블 배정. 빈 자리 없으면 409 |
| DELETE | `/api/kiosk/assignments/{id}` | 손님이 "처음으로"를 눌러 취소 |
| WS | `/api/kiosk/assignments/{id}/guide` | 안내 로봇 상황 `GuideStatus`를 계속 보냄 |
| POST | `/api/staff-calls` | 직원 호출 |
| GET | `/api/menu` | 메뉴 목록 `MenuItem[]` |
| POST | `/api/tables/{tableId}/orders` | `{lines:[{menuId, qty}]}` → `Order` |
| WS | `/api/tables/{tableId}/state` | 테이블 상태 `TableState`를 바뀔 때마다 보냄 (주문 진행, 서빙 로봇 도착) |
| POST | `/api/tables/{tableId}/end-session` | 이용 종료 |

## 시안에 없어서 정한 것

- K1: 인원을 고르기 전에는 주 버튼을 끔. 빈 자리가 없으면 안내 문구
- 직원 호출을 누르면 위쪽에 알림
- T1: 이미 주문이 있으면 "주문 현황" 버튼으로 T3로 돌아갈 수 있음
- T3: "이용 종료" 버튼(T5 확인창을 여는 곳)을 "추가 주문" 옆에 둠
- 이용 종료 뒤 "이용해 주셔서 고마워요" 화면. 직원이 정리를 마치면(서버가 세션을 다시 열면) T1로
- 메뉴 가격은 가짜 API의 예시 값 (치킨 18,000원, 볶음밥 9,000원)
