-- 사전 등록 데이터. 좌표는 실측 전이라 NULL, 테이블 수는 예시(매장 맵 E안 확인 필요)
SET NAMES utf8mb4;
USE frybot;

INSERT INTO location (code, name, type) VALUES
 ('ENT',    '입구',              'ENTRANCE'),
 ('T1',     '테이블1 안내·서빙', 'TABLE'),
 ('T2',     '테이블2 안내·서빙', 'TABLE'),
 ('T3',     '테이블3 안내·서빙', 'TABLE'),
 ('PICKUP', '받는 곳(인계대)',   'PICKUP'),
 ('QUEUE',  '픽업 대기 지점',    'QUEUE'),
 ('DOCK1',  '충전대1',           'DOCK'),
 ('DOCK2',  '충전대2',           'DOCK'),
 ('DOCK3',  '충전대3',           'DOCK');

INSERT INTO dining_table (table_id, code, seats, location_id)
SELECT 1, 'T1', 2, location_id FROM location WHERE code = 'T1' UNION ALL
SELECT 2, 'T2', 4, location_id FROM location WHERE code = 'T2' UNION ALL
SELECT 3, 'T3', 4, location_id FROM location WHERE code = 'T3';

-- SR-009: 치킨, 볶음밥
INSERT INTO menu (name, cook_type) VALUES ('치킨', 'FRY'), ('볶음밥', 'WOK');

-- AMR 3대 + 로봇팔(배치도 기준 2대: 치킨·웍)
INSERT INTO robot (robot_id, type, cook_type, home_location_id)
SELECT 'amr_1', 'AMR', NULL, location_id FROM location WHERE code = 'DOCK1' UNION ALL
SELECT 'amr_2', 'AMR', NULL, location_id FROM location WHERE code = 'DOCK2' UNION ALL
SELECT 'amr_3', 'AMR', NULL, location_id FROM location WHERE code = 'DOCK3';
INSERT INTO robot (robot_id, type, cook_type) VALUES
 ('arm_fry', 'ARM', 'FRY'),
 ('arm_wok', 'ARM', 'WOK');
-- [팀 확인 Q1] SA는 Robot Arm Station × 3. 3대로 정해지면 해제하고 역할을 정한다
-- INSERT INTO robot (robot_id, type, cook_type) VALUES ('arm_3', 'ARM', 'FRY');

-- State Diagram 기준값 N (미정 = NULL)
INSERT INTO system_config (config_key, value, unit, description) VALUES
 ('follow_distance_max', NULL, 'm',  '안내 중 손님과의 최대 거리 (2장 FOLLOW_CHECK)'),
 ('follow_lost_sec',     NULL, 's',  '동행 실패 지속 시간, 넘으면 GUIDE_EXCEPTION (SR-008)'),
 ('auto_receive_sec',    NULL, 's',  '도착 후 자동 수령까지 시간 (5장)'),
 ('battery_charge_pct',  NULL, '%',  '복귀 후 충전 기준 배터리 (5장)'),
 ('stop_tolerance_m',    NULL, 'm',  '정차 허용 오차 (SR-020, SR-024)'),
 ('grasp_retry_max',     1,    '회', '집기 실패 재시도 횟수 (4장)');
