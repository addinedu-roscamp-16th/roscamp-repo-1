# FryBot 저장소 구조 및 통합 검증 검토

## 저장소 구조 결정

FryBot은 단일 저장소에서 `frontend/`, `api/`, `backend/`, `frybot/`의 경계를 유지한다. ROS 2는 패키지별 `package.xml`로 의존성을 선언한다. 공통 액션 계약을 바꾸는 PR에서 정의, 관제 호출부, AMR·팔 구현 및 통합 기동을 함께 검토할 수 있다.

독립 저장소는 장비별 담당 조직, 접근 정책, 배포 일정이 실제로 달라지고 호환 버전을 유지할 책임이 정해졌을 때 검토한다.

## 현재 검증 범위

병합 커밋 `4bf59f4`에서 Python 문법 검사, 웹 문법 검사·테스트·빌드, API Docker 이미지 빌드와 배포 산출물 생성이 성공했다. ROS 2 패키지 8개는 로컬 Jazzy 환경에서 빌드했다. [병합 PR](https://github.com/addinedu-roscamp-16th/roscamp-repo-1/pull/3) · [CI 워크플로](../.github/workflows/frybot-ci.yml)

웹 테스트와 API 이미지 빌드는 각 모듈을 검증한다. OpenAPI의 `POST /visits`, `POST /orders`는 검토 시점의 FastAPI 구현에 없으며, ROS 자체 웹은 별도 HTTP 경로를 사용한다. [OpenAPI 계약](../api/openapi.yaml) · [FastAPI 구현](../backend/api/main.py)

## 개선 순서와 완료 기준

| 우선순위 | 작업 | 완료 기준 |
| --- | --- | --- |
| 1 | 주문에서 ROS 임무까지 연결 | 프론트엔드 → 실제 API → ROS 경량 시뮬레이션을 사용해 방문 접수, 주문 등록, 임무 처리, 서빙 완료 표시를 하나의 자동 테스트로 확인한다. 임무 ID로 주문과 ROS 실행 결과의 대응을 확인한다. |
| 2 | ROS 검증을 CI에 추가 | 기존 워크플로 YAML 한 파일에 Jazzy 빌드와 경량 시뮬레이션 기동 검사를 넣는다. 깨끗한 러너에서 패키지 8개를 빌드하고, 타임아웃 안에 ROS 노드나 서비스가 준비됐는지 확인한다. |
| 3 | 병합 기준을 GitHub에 적용 | 저장소 관리자가 `main`에 PR 승인 1건과 필수 CI를 설정한다. 프론트·백엔드·ROS 변경의 리뷰 담당자를 정하고 규칙 적용을 시험한다. 검토 시점에는 `main`의 보호 및 적용 규칙이 없었다. |
| 4 | 스테이징 배포와 DB 변경 검증 | 새 DB 초기화와 기존 DB 업그레이드를 검증한다. 적용 커밋과 스키마 버전을 기록하고, 기존 버전 복구 후 상태 조회와 핵심 작업이 동작하는지 확인한다. |

[아키텍처와 모듈 경로](ARCHITECTURE.md) · [개발표준](SOURCE_GUIDE.md) · [배포 가이드](DEPLOYMENT_GUIDE.md)
