# FryBot 저장소 구조 및 통합 검증 검토

## 저장소 구조 결정

FryBot은 단일 저장소에서 `frontend/`, `api/`, `backend/`, `frybot/`의 경계를 유지한다. ROS 2는 패키지별 `package.xml`로 의존성을 선언한다. 공통 액션 계약을 바꾸는 PR에서 정의, 관제 호출부, AMR·팔 구현 및 통합 기동을 함께 검토할 수 있다.

독립 저장소는 장비별 담당 조직, 접근 정책, 배포 일정이 실제로 달라지고 호환 버전을 유지할 책임이 정해졌을 때 검토한다.

## 현재 검증 범위

병합 커밋 `4bf59f4`에서 Python 문법 검사, 웹 문법 검사·테스트·빌드, API Docker 이미지 빌드와 배포 산출물 생성이 성공했다. ROS 2 패키지 8개는 로컬 Jazzy 환경에서 빌드했다. [병합 PR](https://github.com/addinedu-roscamp-16th/roscamp-repo-1/pull/3) · [CI 워크플로](../.github/workflows/frybot-ci.yml)

웹 테스트와 API 이미지 빌드는 각 모듈을 검증한다. OpenAPI의 `POST /visits`, `POST /orders`는 검토 시점의 FastAPI 구현에 없으며, ROS 자체 웹은 별도 HTTP 경로를 사용한다. [OpenAPI 계약](../api/openapi.yaml) · [FastAPI 구현](../backend/api/main.py)

## 입력·출력 파라미터

아래는 주문 통합 테스트에서 확인할 HTTP·ROS 경계다. HTTP 필드는 OpenAPI 계약 기준이며, 아직 구현되지 않은 경로는 통합 작업의 목표다. ROS 액션은 목표(Goal), 최종 결과(Result), 진행 피드백(Feedback)을 구분한다.

| 호출 방향·인터페이스 | 입력 | 출력 |
| --- | --- | --- |
| 키오스크 → API · `POST /visits` | `party_size` 정수 1~4, `request_key` 문자열. 둘 다 필수. | HTTP `201`. `visit_id` 문자열, `status`( `WAITING` 또는 `ASSIGNED` ), `table_id` 정수 1~6 또는 `null`, `queue_no` 정수 또는 `null`. 오류 `409`, `422`, `503`. |
| 테이블 화면 → API · `POST /orders` | `visit_id` 문자열, `table_id` 정수 1~6, `items` 배열 1개 이상(각 항목에 `menu_id` 정수, `qty` 정수 1 이상), `request_key` 문자열. 모두 필수. | HTTP `200`. `order_id` 문자열, `status=ORDERED`. 오류 `400`, `409`, `503`. |
| 화면 → API · `GET /visits/{visit_id}/status` | 경로의 `visit_id` 문자열 필수. 쿼리의 `order_id` 문자열 선택. | HTTP `200`. 방문 상태, `orders[]`, `version` 등을 담은 `VisitSnapshot`. 대상이 없으면 `404`. 주문의 `order_id`, `status`, `delivery_step`으로 진행 상태를 확인한다. |
| ROS 호출부 → 관제 · `SubmitTask.srv` | `task_type` 문자열(`GUIDE`, `SERVE`, `COLLECT`, `COOK`), `visit_id`·`order_id`·`item_id`는 `int64`, `table_id`·`priority`는 `int32`, `menu`는 문자열. | `accepted` 불리언, `task_id` 문자열, `message` 문자열. `accepted`는 접수 결과다. |
| 관제 → AMR · `NavigateRoute.action` | Goal에 `task_id`, `robot_id`, `mode` 문자열, `plan_version`(`int32`), `visit_id`(`int64`), `route`(`Waypoint[]`). | Result에 `success`, `plan_version`, `reached_index`, `reason`. Feedback에 `plan_version`, `reached_index`, `state`. |
| 관제 → 조리 팔 · `ArmJob.action` | Goal에 `task_id`, `arm_id`, `job` 문자열, `duration`(`float32`), `params_json` 문자열. 작업별 JSON 키는 액션 정의 참조. | Result에 `success` 불리언, `reason` 문자열. Feedback에 `phase` 문자열, `progress`(`float32`). |

### 시스템 간 계약과 검증 조건

아래 항목은 통합 구현 전에 합의할 계약이다. 위 표의 필드와 응답 코드는 현재 OpenAPI 및 ROS 2 정의를 따른다.

| 계약 항목 | 정의할 내용과 검증 조건 |
| --- | --- |
| 참여자와 책임 | HTTP 호출자는 키오스크·테이블 화면이고 처리자는 FastAPI다. ROS 연동부는 HTTP 방문·주문 문자열 ID를 `SubmitTask`의 `int64` ID와 연결한다. 매핑을 저장하는 모듈과 임무 최종 상태를 갱신하는 모듈을 명시하고, 주문 ID 하나로 ROS `task_id`와 최종 결과를 조회할 수 있는지 검증한다. |
| 수락·진행·완료 | HTTP `ORDERED`는 주문 등록, `SubmitTask.accepted`는 ROS 임무 접수다. AMR·조리 팔 액션의 Feedback은 진행 정보다. 로봇 액션 Result와 서비스의 주문 상태를 어떻게 연결할지 정의하고, 실패·취소가 주문 완료로 전이되지 않는지 확인한다. |
| 시간 초과와 재시도 | 호출별 응답 제한 시간과 작업 완료 기한을 정의한다. 응답을 받지 못하면 기존 처리 상태를 조회하거나 같은 `request_key`로 재요청한다. 키의 적용 범위·보존 기간, 동일 키에 다른 입력이 들어왔을 때의 오류, 재기동 후에도 주문 및 물리 작업이 중복 실행되지 않는 조건을 검증한다. |
| 오류와 권한 | 입력 오류, 대상 없음, 잘못된 상태 전이, 일시 장애, ROS 목표 거절·취소를 구별한다. 오류별 재시도 가능 여부와 응답 형식, 방문·주문 조회 또는 로봇 명령을 허용할 호출자를 정의한다. |
| ROS 데이터와 전달 정책 | 필드별 단위·범위·좌표계와 취소 조건을 인터페이스에 명시한다. 상태를 토픽으로 전달하는 경우 발행자·구독자의 QoS, 갱신 주기, 오래된 상태의 처리 기준을 정한다. |
| 호환성과 추적 | OpenAPI와 ROS 인터페이스를 변경할 때 소비자와 제공자의 배포 순서, 이전 버전 허용 범위, 제거 기준을 정한다. 로그에서 요청 ID, 주문 ID, 임무 ID와 최종 결과를 연계해 응답 유실 및 실행 실패를 재현할 수 있는지 확인한다. |

[HTTP 계약](../api/openapi.yaml) · [SubmitTask](../frybot/frybot_interfaces/srv/SubmitTask.srv) · [NavigateRoute](../frybot/frybot_interfaces/action/NavigateRoute.action) · [ArmJob](../frybot/frybot_interfaces/action/ArmJob.action)

## 개선 순서와 완료 기준

| 우선순위 | 작업 | 완료 기준 |
| --- | --- | --- |
| 1 | 주문에서 ROS 임무까지 연결 | 프론트엔드 → 실제 API → ROS 경량 시뮬레이션을 사용해 방문 접수, 주문 등록, 임무 처리, 서빙 완료 표시를 하나의 자동 테스트로 확인한다. 임무 ID로 주문과 ROS 실행 결과의 대응을 확인한다. |
| 2 | ROS 검증을 CI에 추가 | 기존 워크플로 YAML 한 파일에 Jazzy 빌드와 경량 시뮬레이션 기동 검사를 넣는다. 깨끗한 러너에서 패키지 8개를 빌드하고, 타임아웃 안에 ROS 노드나 서비스가 준비됐는지 확인한다. |
| 3 | 병합 기준을 GitHub에 적용 | 저장소 관리자가 `main`에 PR 승인 1건과 필수 CI를 설정한다. 프론트·백엔드·ROS 변경의 리뷰 담당자를 정하고 규칙 적용을 시험한다. 검토 시점에는 `main`의 보호 및 적용 규칙이 없었다. |
| 4 | 스테이징 배포와 DB 변경 검증 | 새 DB 초기화와 기존 DB 업그레이드를 검증한다. 적용 커밋과 스키마 버전을 기록하고, 기존 버전 복구 후 상태 조회와 핵심 작업이 동작하는지 확인한다. |

[아키텍처와 모듈 경로](ARCHITECTURE.md) · [개발표준](SOURCE_GUIDE.md) · [배포 가이드](DEPLOYMENT_GUIDE.md)
