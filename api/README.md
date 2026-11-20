# api/ — 화면 ↔ Web Service 계약

`openapi.yaml` 이 **기준**입니다. 화면(frontend)과 백엔드(Web Service)는 모두 이 파일 모양대로 주고받습니다.

- 출처: Confluence "1) FryBot I/F 목록"(WEB-01~09)과 "4) Logical Data Model"(상태 이름). 문서에 없던 것은 설명에 `[제안]`.
- 바꿀 때: 이 파일 먼저 → 팀에 알림 → 프론트 `npm run gen:api`, 백엔드도 같은 모양으로.
- 보기: `cd frontend && npm run docs:api` (http://localhost:8090), 또는 https://editor.swagger.io 에 붙여 넣기.
- 검사: 프론트 `npm run lint:api`(문법), `npm test`(목업이 계약을 지키는지), 개발 서버 `/check`(백엔드가 계약을 지키는지).
- 실시간 알림(WebSocket `/ws`)은 OpenAPI로 표현이 안 돼 `SubscribeMessage`·`ServerEvent`·`AdminEvent` 스키마와 설명으로 적었습니다.
