-- FryBot 관제·확인용 조회 쿼리 (읽기 전용, 어느 계정으로도 실행 가능)
-- VSCode SQLTools: 쿼리에 커서를 두고 Ctrl+E Ctrl+E → 현재 쿼리 실행

-- 스키마 버전 (팀원끼리 같은지 확인)
SELECT MAX(version) AS schema_version FROM schema_version;

-- 테이블 현황 (SR-030, SR-032)
SELECT * FROM v_table_board;

-- 주문 진행 (SR-013, SR-015)
SELECT * FROM v_order_progress ORDER BY order_id DESC LIMIT 20;

-- 로봇 현황 (SR-033, SR-037)
SELECT * FROM v_robot_board;

-- 처리 안 된 오류·중단 (SR-036, 7장)
SELECT incident_id, source, robot_id, task_id, order_id, error_code, failed_state, occurred_at
FROM incident WHERE resolved_at IS NULL ORDER BY occurred_at DESC;

-- 대기 중인 임무 (가용 AMR 없음, SR-005·019)
SELECT task_id, task_type, state, created_at FROM task
WHERE state IN ('GUIDE_PENDING','SERVE_PENDING') ORDER BY created_at;

-- 기준값 N (미정이면 NULL)
SELECT config_key, value, unit, description FROM system_config;

-- 최근 운영 이력 (SR-038)
SELECT created_at, entity, entity_id, from_state, to_state, actor, message
FROM event_log ORDER BY log_id DESC LIMIT 50;
