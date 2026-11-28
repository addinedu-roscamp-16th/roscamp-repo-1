# FryBot 개발표준 정의서

FryBot의 프론트엔드, 서버·DB, ROS 2 소스에 적용하는 팀 개발표준입니다. 새 기능, 기존 소스 편입, 인터페이스와 DB 변경에 같은 기준을 적용합니다. 실행 명령과 코드 예제는 표준을 적용할 때 사용합니다.

## 적용 범위와 공통 기준

| 영역 | 기준 | 검토 근거 |
| --- | --- | --- |
| 형상관리·병합 | 작업 브랜치에서 `main` 대상 PR을 열고, 팀원 한 명 이상 승인과 필수 CI 통과 후 병합합니다. | PR 승인과 CI 결과 |
| 인터페이스 | 팀 I/F 목록을 기준으로 HTTP OpenAPI 또는 ROS 2 인터페이스, 구현, 통합 테스트를 대조합니다. | I/F ID, 변경 경로, 실행 결과 |
| DB 변경 | 스키마 변경은 SQL과 함께 리뷰하고, 새 개발 DB와 기존 스키마에서 적용 절차를 확인합니다. | 마이그레이션 명령, 적용·복구 확인 결과 |
| 배포 | 배포 담당자와 대상 환경을 정하고, 적용 버전과 기능 확인 결과를 기록합니다. | 배포 가이드의 팀 채널 스레드 |

코딩·네이밍 세부안은 현재 소스의 관례를 기준으로 합니다. 기존 소스의 예외나 적용하지 못한 검증이 있으면 PR에 사유와 영향 범위를 적습니다. GitHub 필수 검사와 브랜치 보호의 활성화 여부는 저장소 관리자가 확인합니다.

## 아키텍처와 소스 배치

서비스가 연결되면 **React 화면 → FastAPI → MySQL·ROS 2 관제** 흐름으로 동작합니다. 화면은 API를 통해 방문·주문 상태를 읽고, ROS 2는 임무를 처리합니다. 주문·임무 상태를 어느 모듈이 갱신하는지는 통합 PR에서 합의해 기록합니다.

| 경로 | 기술과 역할 |
|---|---|
| `frontend/` | React · TypeScript · Vite. 키오스크·주문 태블릿·관리자 화면은 `src/kiosk`, `src/table`, `src/admin`에서 관리합니다. HTTP 및 WebSocket 연결은 `src/api`에 있습니다. |
| `api/` | `openapi.yaml`의 HTTP 경로·입력·응답 명세. 프론트 TypeScript 타입을 생성할 때 사용합니다. |
| `backend/api/`, `backend/db/` | Python 3.12 · FastAPI · MySQL 8.4. 기존 조회·음성 명령과 SQL 초기화·시드·DB 검증 스크립트가 있습니다. |
| `frybot/` | ROS 2 Jazzy. `frybot_control`은 관제·임무 관리, `frybot_interfaces`는 메시지·서비스·액션, `frybot_bringup`은 시뮬레이션·장비 기동을 담당합니다. |
| `design/` | 화면과 설계 자료. |
| `tools/` | 개발·시험용 도구. `jetcobot_motion_player/`는 로봇팔 동작 공유·조작·재생 웹 도구(Python 표준 라이브러리 서버, 브라우저 3D, RViz)로, 서비스 흐름(React → FastAPI → ROS 2)과 별개로 실행합니다. |

이주헌 님의 ROS 코드에는 **시뮬레이션용 로컬 SQLite와 자체 웹 서버**가 있습니다. FastAPI의 MySQL과 별도 데이터 저장소이며, 자체 웹의 `/api/checkin`·`/api/order` 경로는 React가 호출하는 `/api/visits`·`/api/orders`와 다릅니다. 시뮬레이션 자체 웹으로 로봇 동작을 먼저 독립 검증하고, React 연동 시 상태 갱신 책임과 경로를 확인합니다. [시스템 아키텍처](https://oneteam1.atlassian.net/wiki/spaces/1/pages/786434) · [ROS 자체 웹 구현](https://github.com/addinedu-roscamp-16th/roscamp-repo-1/blob/Juheon_Lee/frybot/frybot_web/frybot_web/web_service_node.py)

저장소 재편 브랜치에는 기존 ROS 이력과 로컬 백엔드·DB를 편입했습니다. GitHub `main`에서 작업할 때는 PR 병합 상태를 확인합니다. [GitHub 저장소](https://github.com/addinedu-roscamp-16th/roscamp-repo-1)

## 의존성 관리

| 모듈 | 기준 파일 | 변경 확인 |
| --- | --- | --- |
| React · TypeScript | `frontend/package.json`과 `package-lock.json` | 의존성을 바꾸면 두 파일을 함께 검토하고 `npm ci`로 재현합니다. |
| FastAPI · MySQL | `backend/api/requirements.txt`, `backend/api/Dockerfile`, `backend/docker-compose.yml` | Python 이미지, Python 패키지 버전, DB 이미지 변경을 구분해 검토합니다. |
| ROS 2 Jazzy | 각 패키지의 `package.xml` 및 `setup.py` 또는 `CMakeLists.txt` | ROS 의존성을 선언하고 `rosdep` 및 `colcon`으로 확인합니다. |

## 개발 환경과 첫 실행

명령은 필요한 모듈별로 실행합니다. 각 블록의 첫 `cd`는 재편 소스가 있는 저장소 루트를 기준으로 합니다.

| 모듈 | 개발 환경 | 로컬 접점 |
|---|---|---|
| 프론트 | Node.js와 npm. Node.js 24·npm 11에서 설치·테스트·빌드를 확인했습니다. | Vite `5173` |
| 서버·DB | Docker Compose, Python 3.12 이미지의 FastAPI, MySQL 8.4 | FastAPI `8000`, MySQL `3306`, Adminer 기본 `8081` |
| 로봇 | Ubuntu 24.04, ROS 2 Jazzy, rosdep, colcon. Gazebo·Nav2 기반 실행은 로봇 실행 문서 참조 | ROS 시뮬레이션 자체 웹 `8080` |

### 프론트엔드

```bash
cd frontend
npm ci
npm run dev
```

`http://localhost:5173/mock/kiosk`, `/mock/table/3`, `/mock/admin`에서 서버 없이 개발용 화면을 확인합니다. 실제 서버 연결은 `frontend/.env`의 `BACKEND_URL`을 설정하고 Vite를 다시 시작한 뒤 `/check`에서 확인합니다. Vite는 개발 중 `/api`와 WebSocket 요청을 전달합니다. 배포용 웹 호스트의 전달 설정은 별도로 구성합니다. [프론트 README](../frontend/README.md)

### FastAPI와 MySQL

```bash
cd backend
cp -n .env.example .env
# .env에 개발용 비밀번호를 설정한 뒤 실행
docker compose up -d --build
curl -fsS http://localhost:8000/health
```

`/health`는 DB에서 스키마 버전을 조회합니다. `http://localhost:8000/docs`에서 현재 등록된 HTTP 경로를 확인합니다. SQL 초기화는 빈 DB 볼륨에서 실행됩니다. 기존 개발 DB에 적용하는 마이그레이션은 PR에 별도 명령과 확인 절차를 적습니다. [백엔드 README](../backend/README.md)

### ROS 2 시뮬레이션

저장소 루트에서 빌드 출력 경로를 개발 작업 공간으로 지정합니다.

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths frybot --ignore-src -r -y
mkdir -p "$HOME/frybot_ws"
colcon --log-base "$HOME/frybot_ws/log" build --base-paths frybot \
  --build-base "$HOME/frybot_ws/build" --install-base "$HOME/frybot_ws/install" \
  --symlink-install --packages-up-to frybot_bringup
source "$HOME/frybot_ws/install/setup.bash"
ros2 launch frybot_bringup sim.launch.py
```

별도 터미널에서 설치 환경을 불러온 뒤 `ros2 run frybot_sim scenario --scenario demo`를 실행합니다. 시뮬레이션은 기본 `net:=sim`을 사용합니다. 실행 인자, 지도와 실기기 절차는 원본 문서에서 확인합니다. [ROS 실행 명령](https://github.com/addinedu-roscamp-16th/roscamp-repo-1/blob/Juheon_Lee/FRYBOT_COMMANDS.md)

### 첫 실행 확인

| 대상 | 확인 방법 | 기대 결과 |
| --- | --- | --- |
| 프론트 목업 | `http://localhost:5173/mock/kiosk` | 인원을 선택해 테이블 배정·대기 안내 표시를 확인합니다. 주문과 관리자 화면은 각각 `/mock/table/3`, `/mock/admin`에서 확인합니다. |
| FastAPI·MySQL | `curl -fsS http://localhost:8000/health` | `ok: true`와 `schema_version`을 확인합니다. 웹 API 연결은 `/check`와 실제 응답으로 별도 확인합니다. |
| ROS 시뮬레이션 | `ros2 run frybot_sim scenario --scenario demo` | 시뮬레이션 자체 웹 또는 시나리오 출력에서 접수·조리·서빙 진행을 확인합니다. |

## 코딩과 네이밍

현재 코드에 맞춰 다음 규칙을 팀 기본안으로 사용합니다.

| 영역 | 규칙과 예 |
|---|---|
| React·TypeScript | 화면 컴포넌트는 `PascalCase`인 `KioskApp.tsx`, 함수는 `camelCase`인 `createVisit`를 사용합니다. 통신과 재연결은 `src/api` 구현을 재사용합니다. |
| FastAPI·Python·SQL | 함수와 데이터 필드는 `snake_case`를 따릅니다. 예를 들어 `voice_command`, `visit_id`, `request_key`를 사용합니다. 입력은 Pydantic 모델에서 검증하고, SQL에 입력값을 전달할 때 매개변수를 사용합니다. |
| OpenAPI | 응답 필드나 상태를 바꾸면 `api/openapi.yaml`과 관련 테스트를 수정한 뒤 `npm run gen:api`로 `schema.gen.ts`를 다시 생성합니다. |
| ROS 2 | 패키지는 `frybot_*`, 인터페이스 파일은 `RobotStatus.msg`, `SubmitTask.srv`, `NavigateRoute.action` 같은 기존 이름 형식을 따릅니다. |

## 주요 기능 코드 예제

[FryBot 방문·주문 실습](../frontend/examples/visit-order/README.md)은 기존 프론트 목업 API와 OpenAPI 명세를 사용해 방문 접수부터 이용 종료까지 확인합니다. `frontend/`에서 `npm run example:visit-order`로 실행합니다.

### 조회 예제 — FastAPI와 MySQL 테이블 현황

아래는 현재 편입된 서버의 `GET /tables` 구현입니다. DB 뷰에서 조회한 결과를 반환합니다. React 명세에는 `/api/tables`로 정의되어 있어 연결 PR에서 접두사 처리와 응답 필드를 맞춥니다.

```python
@app.get('/tables')
def tables():
    with db() as c, c.cursor() as cur:
        cur.execute('SELECT * FROM v_table_board ORDER BY table_id')
        return cur.fetchall()
```

개발 DB가 실행 중일 때 `curl -fsS http://localhost:8000/tables`로 확인합니다. [백엔드 소스 경로](../backend/api/main.py)

### 등록 예제 — 방문 접수에서 주문 등록까지

아래는 기존 프론트 목업 테스트의 핵심 순서를 따라갑니다. `visit_id`로 방문 상태를 조회하고, 같은 방문으로 주문을 등록합니다. 같은 요청을 재전송할 때는 처음 쓴 `request_key`를 유지합니다.

```typescript
const api = createMockApi({ tickMs: 5 })
const visit = await api.createVisit({ party_size: 2, request_key: 'k1' })
if (visit.table_id == null) throw new Error('목업에 배정 가능한 테이블이 필요합니다')

// 기존 테스트에서 안내가 끝나 착석할 때까지 기다리는 부분입니다.
await new Promise((resolve) => setTimeout(resolve, 250))
const seated = await api.getVisit(visit.visit_id)
const order = await api.createOrder({
  visit_id: visit.visit_id,
  table_id: visit.table_id,
  items: [{ menu_id: 1, qty: 1 }],
  request_key: 'k2',
})
```

상태·응답 형식 확인과 구독 해제를 포함한 전체 예제는 테스트 파일에 있습니다. `frontend/`에서 `npm test -- src/api/contract.test.ts`로 확인합니다. 실제 HTTP `POST /api/visits`와 `POST /api/orders`는 현재 FastAPI 편입본의 구현 과제입니다. [방문·주문 목업 테스트](../frontend/src/api/contract.test.ts)

## I/F 변경과 테스트

1. [팀 FryBot I/F 목록](https://oneteam1.atlassian.net/wiki/spaces/1/pages/24641549)에서 I/F ID, 입력·응답, 접수와 완료의 의미를 확인합니다. HTTP는 `api/openapi.yaml`에서 경로·필드·상태 코드를, ROS 2는 `frybot_interfaces/`에서 사용하는 메시지·서비스·액션을 대조합니다.
2. 목록에 있는 개별 주문 조회와 음성 명령은 현재 GitHub OpenAPI 명세에 빠져 있습니다. 명세에 이미 들어간 직원 호출과 관리자 이력·재생은 I/F 목록 채택 여부를 팀과 확인합니다. PR에 **I/F ID / 명세 경로 / 구현 경로 / 확인 결과**를 남깁니다.
3. `frontend/`에서 `npm run lint`, `npm test`, `npm run build`를 실행합니다. 명세 변경 시 `npm run lint:api`와 `npm run gen:api`를 실행하고 생성된 타입과 함께 검토합니다.
4. FastAPI는 `/docs`의 등록 경로와 실제 응답을 각각 대조합니다. 개발 DB의 초기화 후 `backend/`에서 MySQL 클라이언트로 `bash db/tests/run_tests.sh`를 실행할 수 있습니다. 기존 스키마 변경은 준비된 개발 DB에서 검증합니다.
5. ROS 변경은 `colcon build`와 시뮬레이션 시나리오로 확인합니다. 관제 단위 테스트는 빌드한 설치 환경을 불러온 뒤 저장소 루트에서 `python3 -m pytest frybot/frybot_control/test`로 실행합니다. 통합 검증의 기준은 **React 방문 접수 → 주문 등록 → ROS 시뮬레이션 임무 처리 → 화면 서빙 완료**입니다. 요청 재전송과 WebSocket 재접속 후 상태 복원도 확인합니다. 이 전체 흐름의 실제 연동 검증은 남아 있습니다.

## GitHub 협업과 배포

- `git fetch origin`으로 기준을 확인합니다. 기존 작업 브랜치나 PR이 있으면 이어서 사용합니다. 새 브랜치가 필요하면 `git switch -c import/모듈명 origin/main`으로 시작합니다. 소스를 옮길 때 관련 커밋 이력을 보존하고 원본 브랜치나 저장소, SHA를 PR에 남깁니다.
- 커밋 전에 `git status --short`와 `git diff --cached --stat`로 확인합니다. 예제 설정과 필요한 지도·모델은 함께 관리합니다. 개인 `.env`, 실기기 접속 정보, 운영 DB 덤프, `node_modules/`, `dist/`, ROS 빌드 산출물은 커밋 대상에서 제외합니다.
- 작업 브랜치에서 `main` 대상 PR을 열고, 변경 범위·실행 명령·테스트 결과·연관 PR·DB나 지도 적용 순서를 적습니다. 팀원 한 명 이상 승인과 필수 CI 통과 후 병합합니다. GitHub의 필수 검사와 브랜치 보호 적용 여부는 저장소 관리자가 확인합니다.
- 공용 환경 배포는 담당자를 지정하고 환경별 한 건씩 진행합니다. 버전, 적용 순서, 점검, 중단·복구, 사전·종료 공지 양식은 배포 가이드를 따릅니다. [FryBot 배포 가이드](DEPLOYMENT_GUIDE.md)

## 참고 문서

전자정부 표준프레임워크 샘플의 기술 스택·의존성·아키텍처·주요 기능·시작 방법 구성 순서를 참고했습니다. [전자정부 표준프레임워크 5.0 샘플 프로젝트](https://www.egovframe.go.kr/docs/5.0/egovframe-runtime/ai-layer/springai-layer/springai-sample-project/)
