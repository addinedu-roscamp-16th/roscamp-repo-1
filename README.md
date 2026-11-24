# roscamp-repo-1
ROS2와 AI를 활용한 자율주행 로봇개발자 부트캠프 1팀 저장소. 

- [JetCobot 6축 IK 및 시뮬레이터 도입 참고](docs/JETCOBOT_IK_SIMULATION.md)

## 프로젝트 구조

| 경로 | 역할 |
| --- | --- |
| `frontend/` | 키오스크·테이블 주문·관리자 React 화면 |
| `api/` | 프론트엔드와 백엔드가 공유하는 OpenAPI 계약 |
| `backend/` | FastAPI, MySQL 설정과 SQL |
| `frybot/` | AMR·JetCobot·관제·공통 인터페이스·시뮬레이션 등 ROS 2 패키지 8개 |
| `design/` | UI 및 프로젝트 설계 자료 |

[하드웨어·소프트웨어 아키텍처](docs/ARCHITECTURE.md) · [ROS 실행 명령](FRYBOT_COMMANDS.md) · [개발표준](docs/SOURCE_GUIDE.md) · [배포 가이드](docs/DEPLOYMENT_GUIDE.md)

[저장소 구조 및 통합 검증 검토](docs/REPOSITORY_REVIEW.md)
