# FryBot 백엔드와 DB

기존 로컬 FastAPI·MySQL 개발 소스입니다. React 웹 연동은 팀 I/F 목록과 저장소의 [OpenAPI 명세](../api/openapi.yaml)를 기준으로 보완합니다.

```bash
cp .env.example .env
# .env에 개발용 비밀번호를 설정한 뒤 실행
docker compose up -d --build
curl -f http://localhost:8000/health
```

FastAPI 문서는 `http://localhost:8000/docs`에서 봅니다. Adminer 기본 주소는 `http://localhost:8081`이고 `ADMINER_PORT`로 지정할 수 있습니다. ROS 자체 웹의 기본 포트는 8080입니다.

MySQL 초기화 SQL과 개발용 시드는 `db/init/`에 있습니다. 기존 볼륨에 스키마 변경을 적용할 때는 해당 변경의 마이그레이션 절차를 따릅니다. [개념 모델](docs/01_개념모델.md) · [논리 모델](docs/02_논리모델.md)
