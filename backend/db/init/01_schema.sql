-- =====================================================================
-- FryBot 물리 스키마 v3  (MySQL 8.4)
-- 근거: docs/01_개념모델.md, docs/02_논리모델.md
--       SR v6 (SR-001~038), State Diagram v3 (상태 이름은 원본 그대로)
-- 규칙: State Diagram / SR에 근거가 없는 DB 전용 항목은
--       "-- [DB 제안]" 주석으로 남겨 두고 팀 결정 후 해제한다.
-- =====================================================================
SET NAMES utf8mb4;
USE frybot;

-- ---------------------------------------------------------------------
-- 위치: 로봇 이동 지점 (SR-002 안내·서빙 위치, SR-020 적재 위치)
-- ---------------------------------------------------------------------
CREATE TABLE location (
  location_id  INT AUTO_INCREMENT PRIMARY KEY,
  code         VARCHAR(20) NOT NULL UNIQUE,
  name         VARCHAR(50) NOT NULL,
  type         ENUM('ENTRANCE','TABLE','PICKUP','QUEUE','DOCK') NOT NULL
               COMMENT 'PICKUP=받는 곳·인계대, QUEUE=대기 지점, DOCK=충전대',
  x            DOUBLE NULL COMMENT 'map 좌표(m), 실측 전 NULL',
  y            DOUBLE NULL,
  yaw          DOUBLE NULL
) COMMENT '로봇 이동 지점';

-- ---------------------------------------------------------------------
-- 테이블 (SR-002~004, SR-028~031 / State Diagram 2·6장)
-- 주체: 서버/고객·테이블·주문 관리
-- ---------------------------------------------------------------------
CREATE TABLE dining_table (
  table_id     INT PRIMARY KEY,
  code         VARCHAR(10) NOT NULL UNIQUE,
  seats        INT NOT NULL CHECK (seats >= 1),
  location_id  INT NOT NULL UNIQUE COMMENT '안내·서빙 위치',
  status       ENUM('AVAILABLE','ASSIGNED','IN_USE','CLEANING') NOT NULL DEFAULT 'AVAILABLE',
  updated_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  FOREIGN KEY (location_id) REFERENCES location(location_id)
) COMMENT '테이블';

-- ---------------------------------------------------------------------
-- 손님 그룹 (SR-001 / State Diagram 2·6장)
-- 주체: 입구 접수 UI(CHECK_IN) → 서버/고객·테이블·주문 관리
-- ---------------------------------------------------------------------
CREATE TABLE visit (
  visit_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  party_size   INT NOT NULL CHECK (party_size >= 1),
  queue_no     INT NULL COMMENT '대기 순번(WAITING)',
  table_id     INT NULL,
  status       ENUM('CHECK_IN','WAITING','ASSIGNED','IN_USE','END_OF_USE'
                 -- [DB 제안] ,'CANCELED'   -- 대기 이탈·안내 포기. State Diagram에 없음
               ) NOT NULL DEFAULT 'CHECK_IN',
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  ended_at     DATETIME(3) NULL,
  -- SR-004: 같은 테이블에 진행 중(ASSIGNED, IN_USE) 손님 그룹은 1개
  active_table_id INT GENERATED ALWAYS AS
    (CASE WHEN status IN ('ASSIGNED','IN_USE') THEN table_id END) STORED,
  UNIQUE KEY uk_visit_active_table (active_table_id),
  KEY idx_visit_status (status),
  CONSTRAINT chk_visit_table CHECK (status NOT IN ('ASSIGNED','IN_USE') OR table_id IS NOT NULL),
  FOREIGN KEY (table_id) REFERENCES dining_table(table_id)
) COMMENT '손님 그룹';

-- ---------------------------------------------------------------------
-- 메뉴 (SR-009, SR-016·017)
-- ---------------------------------------------------------------------
CREATE TABLE menu (
  menu_id      INT AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(50) NOT NULL UNIQUE,
  cook_type    ENUM('FRY','WOK') NOT NULL COMMENT '조리할 로봇팔 선택 기준',
  is_available BOOLEAN NOT NULL DEFAULT TRUE COMMENT '품절이면 주문 오류(3장)'
  -- [DB 제안] , price    INT NULL CHECK (price >= 0)      -- 결제 범위 밖
  -- [DB 제안] , cook_sec INT NULL CHECK (cook_sec >= 1)   -- 표준 조리 시간(ETA용)
) COMMENT '메뉴';

-- ---------------------------------------------------------------------
-- 주문 (SR-010~013 / State Diagram 3장)
-- 주체: 서버/고객·테이블·주문 관리 (Workflow 보고 반영)
-- ---------------------------------------------------------------------
CREATE TABLE orders (
  order_id     BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '고유 주문 ID(SR-012)',
  visit_id     BIGINT NOT NULL,
  table_id     INT NOT NULL COMMENT '주문 화면의 테이블(SR-010)',
  status       ENUM('ORDERED','COOKING','READY','SERVING','ARRIVED','COMPLETED','ON_HOLD','CANCELED')
               NOT NULL DEFAULT 'ORDERED',
  hold_from_status ENUM('ORDERED','COOKING','READY','SERVING','ARRIVED') NULL
               COMMENT 'ON_HOLD 직전 상태. 재시도 시 여기로 복귀',
  received_by  ENUM('CUSTOMER','AUTO') NULL COMMENT '수령 확인 / N초 후 자동 수령',
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  completed_at DATETIME(3) NULL,
  KEY idx_orders_status (status),
  KEY idx_orders_created (created_at),
  CONSTRAINT chk_orders_hold CHECK ((status = 'ON_HOLD') = (hold_from_status IS NOT NULL)),
  CONSTRAINT chk_orders_done CHECK (status <> 'COMPLETED' OR received_by IS NOT NULL),
  FOREIGN KEY (visit_id) REFERENCES visit(visit_id),
  FOREIGN KEY (table_id) REFERENCES dining_table(table_id)
) COMMENT '주문';

-- ---------------------------------------------------------------------
-- 주문 항목 (SR-014 메뉴별 조리 작업, SR-015 항목별 서빙 준비)
-- ---------------------------------------------------------------------
CREATE TABLE order_item (
  order_item_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_id     BIGINT NOT NULL,
  menu_id      INT NOT NULL,
  qty          INT NOT NULL DEFAULT 1 CHECK (qty >= 1),
  ready_at     DATETIME(3) NULL COMMENT '서빙 준비 완료(인계대 ON_HANDOFF)',
  serve_task_id BIGINT NULL COMMENT '이 항목을 싣고 간 서빙 임무',
  UNIQUE KEY uk_order_menu (order_id, menu_id),
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (menu_id) REFERENCES menu(menu_id)
  -- serve_task_id FK는 task 생성 후 ALTER로 추가
) COMMENT '주문 항목';

-- ---------------------------------------------------------------------
-- 로봇 (SR-033, SR-037)
-- state: State Diagram AMR·로봇팔 레인 상태. 주체: 장치 보고 → Workflow 저장
-- ---------------------------------------------------------------------
CREATE TABLE robot (
  robot_id     VARCHAR(20) PRIMARY KEY COMMENT 'ROS2 네임스페이스와 같게',
  type         ENUM('AMR','ARM') NOT NULL,
  cook_type    ENUM('FRY','WOK') NULL COMMENT '로봇팔만',
  state        ENUM(
                 'IDLE','E_STOP',
                 -- AMR (2·5장)
                 'TO_ENTRANCE','GUIDING','PAUSED','ARRIVED','RETURNING','CHARGING',
                 'TO_PICKUP','QUEUED','DOCKED','SERVING',
                 -- 로봇팔 (4·5장)
                 'PICK_CHICKEN','FRYING','WAIT_TIMER','LIFT_AND_DRAIN',
                 'PICK_INGREDIENTS','STIR_FRYING','PLATING','ON_HANDOFF','RETRY','LOADING'
                 -- [DB 제안] ,'OFFLINE'   -- 보고 끊김. 지금은 last_seen_at으로 판단
               ) NOT NULL DEFAULT 'IDLE',
  home_location_id INT NULL COMMENT 'AMR 충전대',
  pose_x       DOUBLE NULL,
  pose_y       DOUBLE NULL,
  pose_yaw     DOUBLE NULL,
  battery_pct  INT NULL CHECK (battery_pct BETWEEN 0 AND 100),
  is_charging  BOOLEAN NULL COMMENT 'SR-037: 복귀(RETURNING→도착)와 실제 충전을 구분',
  last_seen_at DATETIME(3) NULL,
  CONSTRAINT chk_robot_type_state CHECK (
       state IN ('IDLE','E_STOP')
    OR (type = 'AMR' AND state IN ('TO_ENTRANCE','GUIDING','PAUSED','ARRIVED','RETURNING','CHARGING',
                                   'TO_PICKUP','QUEUED','DOCKED','SERVING'))
    OR (type = 'ARM' AND state IN ('PICK_CHICKEN','FRYING','WAIT_TIMER','LIFT_AND_DRAIN',
                                   'PICK_INGREDIENTS','STIR_FRYING','PLATING','ON_HANDOFF','RETRY','LOADING'))
  ),
  CONSTRAINT chk_robot_cook_type CHECK ((type = 'ARM') = (cook_type IS NOT NULL)),
  FOREIGN KEY (home_location_id) REFERENCES location(location_id)
) COMMENT '로봇';

-- ---------------------------------------------------------------------
-- 임무 (SR-005, SR-014, SR-018·019, SR-034 / State Diagram 2·4·5·7장)
-- state: Service Workflow 레인 상태. 진행 중 세부 단계는 robot.state
-- ---------------------------------------------------------------------
CREATE TABLE task (
  task_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_type    ENUM('GUIDE','COOK','SERVE') NOT NULL,
  state        ENUM('GUIDE_REQ','GUIDE_PENDING','GUIDE_EXCEPTION',
                    'COOK_TASK',
                    'SERVE_REQ','SERVE_PENDING',
                    'ON_HOLD','RECOVERY_WAIT','CHECK','RESUME',
                    'CANCEL_TASK','REASSIGN','CANCELED'
                    -- [DB 제안] ,'DONE'   -- 완료 상태 없음. 지금은 finished_at으로 표시
               ) NOT NULL,
  hold_from_state ENUM('GUIDE_REQ','COOK_TASK','SERVE_REQ','RESUME') NULL COMMENT 'ON_HOLD 직전 상태',
  robot_id     VARCHAR(20) NULL,
  visit_id     BIGINT NULL COMMENT 'GUIDE 대상',
  order_item_id BIGINT NULL COMMENT 'COOK 대상',
  order_id     BIGINT NULL COMMENT 'SERVE 대상',
  reassigned_from_task_id BIGINT NULL COMMENT 'SR-034 재배정 전 임무',
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  assigned_at  DATETIME(3) NULL,
  finished_at  DATETIME(3) NULL COMMENT '완료 시각(완료 표시)',
  -- 로봇 1대에 진행 중 임무 1건: 배정됨 + 미완료 + 재배정/취소 아님
  active_robot_id VARCHAR(20) GENERATED ALWAYS AS (
    CASE WHEN finished_at IS NULL AND state NOT IN ('REASSIGN','CANCELED') THEN robot_id END
  ) STORED,
  UNIQUE KEY uk_task_active_robot (active_robot_id),
  KEY idx_task_state (state),
  KEY idx_task_created (created_at),
  CONSTRAINT chk_task_target CHECK (
       (task_type = 'GUIDE' AND visit_id IS NOT NULL AND order_item_id IS NULL AND order_id IS NULL)
    OR (task_type = 'COOK'  AND order_item_id IS NOT NULL AND visit_id IS NULL AND order_id IS NULL)
    OR (task_type = 'SERVE' AND order_id IS NOT NULL AND visit_id IS NULL AND order_item_id IS NULL)
  ),
  CONSTRAINT chk_task_type_state CHECK (
       (state IN ('GUIDE_REQ','GUIDE_PENDING','GUIDE_EXCEPTION') AND task_type = 'GUIDE')
    OR (state = 'COOK_TASK' AND task_type = 'COOK')
    OR (state IN ('SERVE_REQ','SERVE_PENDING') AND task_type = 'SERVE')
    OR (state IN ('ON_HOLD','RECOVERY_WAIT','CHECK','RESUME','CANCEL_TASK','REASSIGN','CANCELED'))
  ),
  CONSTRAINT chk_task_pending_robot CHECK (state NOT IN ('GUIDE_PENDING','SERVE_PENDING') OR robot_id IS NULL),
  CONSTRAINT chk_task_hold CHECK ((state = 'ON_HOLD') = (hold_from_state IS NOT NULL)),
  CONSTRAINT chk_task_reassign CHECK (reassigned_from_task_id IS NULL OR task_type IN ('GUIDE','SERVE')),
  FOREIGN KEY (robot_id) REFERENCES robot(robot_id),
  FOREIGN KEY (visit_id) REFERENCES visit(visit_id),
  FOREIGN KEY (order_item_id) REFERENCES order_item(order_item_id),
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (reassigned_from_task_id) REFERENCES task(task_id)
) COMMENT '임무';

ALTER TABLE order_item
  ADD CONSTRAINT fk_order_item_serve_task FOREIGN KEY (serve_task_id) REFERENCES task(task_id);

-- ---------------------------------------------------------------------
-- 오류·복구 기록 (SR-036, SR-034 / State Diagram 7장)
-- ---------------------------------------------------------------------
CREATE TABLE incident (
  incident_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  source       ENUM('DEVICE_ERROR','ADMIN_STOP') NOT NULL COMMENT '오류 발생 / 관리자 중단',
  robot_id     VARCHAR(20) NOT NULL COMMENT '장치 식별자',
  task_id      BIGINT NULL,
  order_id     BIGINT NULL,
  error_code   VARCHAR(30) NULL,
  error_message VARCHAR(500) NULL,
  failed_state VARCHAR(30) NULL COMMENT '실패한 작업 단계(당시 robot.state)',
  admin_choice ENUM('RETRY','STOP') NULL COMMENT '관리자 선택',
  result       ENUM('RESUME','REASSIGN','CANCELED') NULL COMMENT '7장 처리 결과',
  occurred_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  resolved_at  DATETIME(3) NULL,
  KEY idx_incident_open (resolved_at),
  CONSTRAINT chk_incident_error CHECK (source <> 'DEVICE_ERROR' OR error_code IS NOT NULL),
  CONSTRAINT chk_incident_resolved CHECK ((resolved_at IS NULL) = (result IS NULL)),
  FOREIGN KEY (robot_id) REFERENCES robot(robot_id),
  FOREIGN KEY (task_id) REFERENCES task(task_id),
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
) COMMENT '오류·복구 기록';

-- ---------------------------------------------------------------------
-- AI 판단 결과 (State Diagram 2장 FOLLOW_CHECK, 4장 DONENESS)
-- ---------------------------------------------------------------------
CREATE TABLE vision_result (
  result_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id      BIGINT NOT NULL,
  robot_id     VARCHAR(20) NOT NULL COMMENT '영상을 보낸 장치',
  kind         ENUM('FOLLOW_CHECK','DONENESS') NOT NULL,
  decision     VARCHAR(20) NOT NULL COMMENT 'FOLLOW_CHECK: NEAR/FAR/LOST, DONENESS: DONE/UNDERCOOKED',
  confidence   DECIMAL(5,4) NULL,
  model_version VARCHAR(50) NULL,
  detail       JSON NULL,
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  CONSTRAINT chk_vision_decision CHECK (
       (kind = 'FOLLOW_CHECK' AND decision IN ('NEAR','FAR','LOST'))
    OR (kind = 'DONENESS'     AND decision IN ('DONE','UNDERCOOKED'))
  ),
  FOREIGN KEY (task_id) REFERENCES task(task_id),
  FOREIGN KEY (robot_id) REFERENCES robot(robot_id)
) COMMENT 'AI 판단 결과';

-- ---------------------------------------------------------------------
-- 기준값 N (State Diagram 확인 사항 4)
-- ---------------------------------------------------------------------
CREATE TABLE system_config (
  config_key   VARCHAR(50) PRIMARY KEY,
  value        DECIMAL(10,3) NULL COMMENT '미정이면 NULL',
  unit         VARCHAR(10) NOT NULL,
  description  VARCHAR(200) NOT NULL,
  updated_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) COMMENT '기준값';

-- ---------------------------------------------------------------------
-- 운영 이력 (SR-038). actor = State Diagram 레인
-- ---------------------------------------------------------------------
CREATE TABLE event_log (
  log_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  entity       ENUM('VISIT','TABLE','ORDER','TASK','ROBOT','INCIDENT') NOT NULL,
  entity_id    VARCHAR(30) NOT NULL,
  from_state   VARCHAR(30) NULL,
  to_state     VARCHAR(30) NULL,
  actor        ENUM('ENTRANCE_UI','TABLE_UI','ADMIN_UI','ORDER_MANAGER','WORKFLOW','AI_SERVER','AMR','ARM') NOT NULL,
  message      VARCHAR(500) NULL,
  detail       JSON NULL,
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_log_time (created_at),
  KEY idx_log_entity (entity, entity_id)
) COMMENT '운영 이력';

-- ---------------------------------------------------------------------
-- [DB 제안] ETA 예측 — SR·State Diagram 근거 없음. Colab ETA 학습을 범위에 넣으면 해제
-- ---------------------------------------------------------------------
-- CREATE TABLE eta_prediction (
--   prediction_id BIGINT AUTO_INCREMENT PRIMARY KEY,
--   order_id      BIGINT NOT NULL,
--   stage         ENUM('ON_ORDER','ON_READY') NOT NULL,
--   predicted_sec INT NOT NULL,
--   model_version VARCHAR(50) NOT NULL,
--   created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
--   FOREIGN KEY (order_id) REFERENCES orders(order_id)
-- ) COMMENT 'ETA 예측';

CREATE TABLE schema_version (
  version      INT PRIMARY KEY,
  description  VARCHAR(200) NOT NULL,
  applied_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 조회용 뷰
-- =====================================================================
-- SR-030, SR-032: 테이블 현황
CREATE VIEW v_table_board AS
SELECT t.table_id, t.code AS table_code, t.seats, t.status AS table_status,
       v.visit_id, v.party_size, v.status AS visit_status,
       (SELECT COUNT(*) FROM orders o
         WHERE o.table_id = t.table_id AND o.visit_id = v.visit_id
           AND o.status NOT IN ('COMPLETED','CANCELED')) AS open_orders
FROM dining_table t
LEFT JOIN visit v ON v.active_table_id = t.table_id;

-- SR-013, SR-015: 주문 진행
CREATE VIEW v_order_progress AS
SELECT o.order_id, t.code AS table_code, o.status, o.hold_from_status,
       COUNT(oi.order_item_id)  AS item_count,
       COUNT(oi.ready_at)       AS ready_count,
       COUNT(oi.serve_task_id)  AS loaded_count,
       o.created_at, o.completed_at
FROM orders o
JOIN dining_table t ON t.table_id = o.table_id
LEFT JOIN order_item oi ON oi.order_id = o.order_id
GROUP BY o.order_id, t.code, o.status, o.hold_from_status, o.created_at, o.completed_at;

-- SR-033, SR-037: 로봇 현황
CREATE VIEW v_robot_board AS
SELECT r.robot_id, r.type, r.cook_type, r.state, r.battery_pct, r.is_charging,
       r.pose_x, r.pose_y, r.last_seen_at,
       t.task_id, t.task_type, t.state AS task_state
FROM robot r
LEFT JOIN task t ON t.active_robot_id = r.robot_id;

INSERT INTO schema_version (version, description) VALUES
 (1, 'initial draft'),
 (2, 'conceptual/logical model v0.2'),
 (3, 'aligned to SR v6 + State Diagram v3; DB-only items commented');
