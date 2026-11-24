#!/usr/bin/env bash
# FryBot DB 스키마 검증 (State Diagram 시나리오 + SR 규칙)
# 사용: ./db/tests/run_tests.sh [호스트]   (기본 127.0.0.1, 계정 team_dev)
# 모든 케이스는 트랜잭션 안에서 실행 후 ROLLBACK → 데이터가 남지 않는다.
set -u
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
HOST="${1:-127.0.0.1}"
PASS=0; FAIL=0

run() { mysql -h"$HOST" -P3306 -uteam_dev -p"$TEAM_DEV_PASSWORD" frybot -N -B 2>&1 \
          -e "START TRANSACTION; $1; ROLLBACK;" | grep -v 'Using a password'; }

ok() {   # ok "설명" "SQL" "기대 출력(선택)"
  out=$(run "$2")
  if echo "$out" | grep -q '^ERROR'; then echo "  ✗ $1"; echo "      $out"; FAIL=$((FAIL+1))
  elif [ -n "${3:-}" ] && [ "$(echo "$out" | tail -1)" != "$3" ]; then
       echo "  ✗ $1 (기대: $3 / 실제: $(echo "$out" | tail -1))"; FAIL=$((FAIL+1))
  else echo "  ✓ $1"; PASS=$((PASS+1)); fi
}
deny() { # deny "설명" "SQL" "기대 오류 일부"
  out=$(run "$2")
  if echo "$out" | grep -q "$3"; then echo "  ✓ $1 → 거부됨"; PASS=$((PASS+1))
  else echo "  ✗ $1 (거부되지 않음) $out"; FAIL=$((FAIL+1)); fi
}

# 공통 준비: 손님 그룹 + 테이블 배정 + 주문(치킨1, 볶음밥2)
SETUP="INSERT INTO visit(party_size) VALUES(2); SET @v=LAST_INSERT_ID();
UPDATE visit SET status='ASSIGNED', table_id=1 WHERE visit_id=@v;
UPDATE dining_table SET status='ASSIGNED' WHERE table_id=1;
INSERT INTO orders(visit_id,table_id) VALUES(@v,1); SET @o=LAST_INSERT_ID();
INSERT INTO order_item(order_id,menu_id,qty) SELECT @o,menu_id,1 FROM menu WHERE name='치킨';  SET @i1=LAST_INSERT_ID();
INSERT INTO order_item(order_id,menu_id,qty) SELECT @o,menu_id,2 FROM menu WHERE name='볶음밥'; SET @i2=LAST_INSERT_ID()"

echo "■ 정상 흐름 (State Diagram 2~6장)"
ok "2장 입장: CHECK_IN → 만석이면 WAITING" \
   "INSERT INTO visit(party_size) VALUES(3); UPDATE visit SET status='WAITING', queue_no=1 WHERE visit_id=LAST_INSERT_ID(); SELECT status FROM visit ORDER BY visit_id DESC LIMIT 1" "WAITING"
ok "2장 안내: GUIDE_REQ + AMR 배정 → GUIDING → 착석 IN_USE" \
   "$SETUP; INSERT INTO task(task_type,state,visit_id,robot_id,assigned_at) VALUES('GUIDE','GUIDE_REQ',@v,'amr_1',NOW(3)); SET @g=LAST_INSERT_ID();
    UPDATE robot SET state='GUIDING' WHERE robot_id='amr_1';
    INSERT INTO vision_result(task_id,robot_id,kind,decision) VALUES(@g,'amr_1','FOLLOW_CHECK','NEAR');
    UPDATE task SET finished_at=NOW(3) WHERE task_id=@g; UPDATE robot SET state='RETURNING' WHERE robot_id='amr_1';
    UPDATE visit SET status='IN_USE' WHERE visit_id=@v; UPDATE dining_table SET status='IN_USE' WHERE table_id=1;
    SELECT CONCAT(table_status,'/',visit_status) FROM v_table_board WHERE table_id=1" "IN_USE/IN_USE"
ok "2장 가용 AMR 없음: GUIDE_PENDING (로봇 미배정)" \
   "$SETUP; INSERT INTO task(task_type,state,visit_id) VALUES('GUIDE','GUIDE_PENDING',@v); SELECT state FROM task WHERE task_id=LAST_INSERT_ID()" "GUIDE_PENDING"
ok "3·4장 주문 → 메뉴별 COOK_TASK 2건 → 조리 → 인계대(ready_at)" \
   "$SETUP; UPDATE orders SET status='COOKING' WHERE order_id=@o;
    INSERT INTO task(task_type,state,order_item_id,robot_id) VALUES('COOK','COOK_TASK',@i1,'arm_fry'),('COOK','COOK_TASK',@i2,'arm_wok');
    UPDATE robot SET state='FRYING' WHERE robot_id='arm_fry'; UPDATE robot SET state='STIR_FRYING' WHERE robot_id='arm_wok';
    INSERT INTO vision_result(task_id,robot_id,kind,decision,confidence) SELECT task_id,'arm_fry','DONENESS','UNDERCOOKED',0.81 FROM task WHERE order_item_id=@i1;
    UPDATE order_item SET ready_at=NOW(3) WHERE order_id=@o; UPDATE task SET finished_at=NOW(3) WHERE task_type='COOK' AND order_item_id IN (@i1,@i2);
    UPDATE orders SET status='READY' WHERE order_id=@o;
    SELECT CONCAT(status,' ',ready_count,'/',item_count) FROM v_order_progress WHERE order_id=@o" "READY 2/2"
ok "5장 SERVE_REQ → DOCKED → LOADING(로봇팔) → SERVING → ARRIVED → 자동 수령 COMPLETED" \
   "$SETUP; UPDATE order_item SET ready_at=NOW(3) WHERE order_id=@o; UPDATE orders SET status='READY' WHERE order_id=@o;
    INSERT INTO task(task_type,state,order_id,robot_id) VALUES('SERVE','SERVE_REQ',@o,'amr_2'); SET @s=LAST_INSERT_ID();
    UPDATE robot SET state='DOCKED' WHERE robot_id='amr_2'; UPDATE robot SET state='LOADING' WHERE robot_id='arm_fry';
    UPDATE order_item SET serve_task_id=@s WHERE order_id=@o; UPDATE orders SET status='SERVING' WHERE order_id=@o;
    UPDATE robot SET state='ARRIVED' WHERE robot_id='amr_2'; UPDATE orders SET status='ARRIVED' WHERE order_id=@o;
    UPDATE orders SET status='COMPLETED', received_by='AUTO', completed_at=NOW(3) WHERE order_id=@o; UPDATE task SET finished_at=NOW(3) WHERE task_id=@s;
    SELECT CONCAT(status,' ',loaded_count) FROM v_order_progress WHERE order_id=@o" "COMPLETED 2"
ok "6장 이용 종료 → CLEANING → 관리자 정리 완료 → AVAILABLE" \
   "$SETUP; UPDATE visit SET status='IN_USE' WHERE visit_id=@v; UPDATE orders SET status='COMPLETED', received_by='CUSTOMER' WHERE order_id=@o;
    UPDATE visit SET status='END_OF_USE', ended_at=NOW(3) WHERE visit_id=@v; UPDATE dining_table SET status='CLEANING' WHERE table_id=1;
    UPDATE dining_table SET status='AVAILABLE' WHERE table_id=1; SELECT status FROM dining_table WHERE table_id=1" "AVAILABLE"
ok "6장 이용 종료 후 같은 테이블에 새 손님 배정 가능" \
   "$SETUP; UPDATE visit SET status='END_OF_USE' WHERE visit_id=@v; INSERT INTO visit(party_size,table_id,status) VALUES(2,1,'ASSIGNED'); SELECT COUNT(*) FROM visit WHERE active_table_id=1" "1"

echo "■ 오류·복구 (State Diagram 7장, SR-034·036)"
ok "AMR 오류: E_STOP → 주문·임무 ON_HOLD → RECOVERY_WAIT → CHECK → RESUME(멈춘 단계)" \
   "$SETUP; UPDATE orders SET status='SERVING' WHERE order_id=@o;
    INSERT INTO task(task_type,state,order_id,robot_id) VALUES('SERVE','SERVE_REQ',@o,'amr_2'); SET @s=LAST_INSERT_ID();
    UPDATE robot SET state='E_STOP' WHERE robot_id='amr_2';
    INSERT INTO incident(source,robot_id,task_id,order_id,error_code,error_message,failed_state) VALUES('DEVICE_ERROR','amr_2',@s,@o,'NAV_BLOCKED','경로 막힘','SERVING'); SET @e=LAST_INSERT_ID();
    UPDATE orders SET status='ON_HOLD', hold_from_status='SERVING' WHERE order_id=@o;
    UPDATE task SET state='ON_HOLD', hold_from_state='SERVE_REQ' WHERE task_id=@s;
    UPDATE task SET state='RECOVERY_WAIT', hold_from_state=NULL WHERE task_id=@s;
    UPDATE incident SET admin_choice='RETRY' WHERE incident_id=@e; UPDATE task SET state='CHECK' WHERE task_id=@s; UPDATE task SET state='RESUME' WHERE task_id=@s;
    UPDATE orders SET status=hold_from_status, hold_from_status=NULL WHERE order_id=@o;
    UPDATE incident SET result='RESUME', resolved_at=NOW(3) WHERE incident_id=@e;
    SELECT CONCAT(o.status,'/',t.state,'/',i.result) FROM orders o, task t, incident i WHERE o.order_id=@o AND t.task_id=@s AND i.incident_id=@e" "SERVING/RESUME/RESUME"
ok "관리자 중단: AMR 임무 CANCEL_TASK → REASSIGN → 다른 AMR에 새 임무" \
   "$SETUP; INSERT INTO task(task_type,state,order_id,robot_id) VALUES('SERVE','SERVE_REQ',@o,'amr_2'); SET @s=LAST_INSERT_ID();
    INSERT INTO incident(source,robot_id,task_id,order_id) VALUES('ADMIN_STOP','amr_2',@s,@o); SET @e=LAST_INSERT_ID();
    UPDATE task SET state='CANCEL_TASK' WHERE task_id=@s; UPDATE task SET state='REASSIGN' WHERE task_id=@s;
    INSERT INTO task(task_type,state,order_id,robot_id,reassigned_from_task_id) VALUES('SERVE','SERVE_REQ',@o,'amr_3',@s);
    UPDATE incident SET admin_choice='STOP', result='REASSIGN', resolved_at=NOW(3) WHERE incident_id=@e;
    SELECT robot_id FROM task WHERE reassigned_from_task_id=@s" "amr_3"
ok "관리자 중단: 조리 임무 CANCELED → 주문 CANCELED" \
   "$SETUP; INSERT INTO task(task_type,state,order_item_id,robot_id) VALUES('COOK','COOK_TASK',@i1,'arm_fry'); SET @c=LAST_INSERT_ID();
    UPDATE orders SET status='ON_HOLD', hold_from_status='COOKING' WHERE order_id=@o;
    UPDATE task SET state='CANCELED' WHERE task_id=@c; UPDATE orders SET status='CANCELED', hold_from_status=NULL WHERE order_id=@o;
    SELECT status FROM orders WHERE order_id=@o" "CANCELED"
ok "중단 후 로봇이 새 임무를 받을 수 있음 (REASSIGN 상태는 점유 해제)" \
   "$SETUP; INSERT INTO task(task_type,state,order_id,robot_id) VALUES('SERVE','REASSIGN',@o,'amr_1');
    INSERT INTO task(task_type,state,visit_id,robot_id) VALUES('GUIDE','GUIDE_REQ',@v,'amr_1'); SELECT task_type FROM v_robot_board WHERE robot_id='amr_1'" "GUIDE"

echo "■ 금지 규칙 (DB가 막아야 하는 것)"
deny "SR-004 같은 테이블에 진행 중 손님 2팀" \
     "$SETUP; INSERT INTO visit(party_size,table_id,status) VALUES(2,1,'IN_USE')" "uk_visit_active_table"
deny "배정 상태인데 테이블 없음" \
     "INSERT INTO visit(party_size,status) VALUES(2,'ASSIGNED')" "chk_visit_table"
deny "로봇 1대에 진행 중 임무 2건" \
     "$SETUP; INSERT INTO task(task_type,state,visit_id,robot_id) VALUES('GUIDE','GUIDE_REQ',@v,'amr_1');
      INSERT INTO task(task_type,state,order_id,robot_id) VALUES('SERVE','SERVE_REQ',@o,'amr_1')" "uk_task_active_robot"
deny "조리 임무에 주문 항목 없음" \
     "INSERT INTO task(task_type,state) VALUES('COOK','COOK_TASK')" "chk_task_target"
deny "유형과 맞지 않는 상태 (조리 임무가 SERVE_REQ)" \
     "$SETUP; INSERT INTO task(task_type,state,order_item_id) VALUES('COOK','SERVE_REQ',@i1)" "chk_task_type_state"
deny "대기(PENDING) 임무에 로봇 배정" \
     "$SETUP; INSERT INTO task(task_type,state,visit_id,robot_id) VALUES('GUIDE','GUIDE_PENDING',@v,'amr_1')" "chk_task_pending_robot"
deny "조리 임무 재배정 (7장: 조리는 주문 취소)" \
     "$SETUP; INSERT INTO task(task_type,state,order_item_id) VALUES('COOK','REASSIGN',@i1); INSERT INTO task(task_type,state,order_item_id,reassigned_from_task_id) VALUES('COOK','COOK_TASK',@i1,LAST_INSERT_ID())" "chk_task_reassign"
deny "ON_HOLD인데 복귀할 상태 없음" \
     "$SETUP; UPDATE orders SET status='ON_HOLD' WHERE order_id=@o" "chk_orders_hold"
deny "수령 방식 없이 COMPLETED" \
     "$SETUP; UPDATE orders SET status='COMPLETED' WHERE order_id=@o" "chk_orders_done"
deny "AMR에 로봇팔 상태(FRYING)" \
     "UPDATE robot SET state='FRYING' WHERE robot_id='amr_1'" "chk_robot_type_state"
deny "State Diagram에 없는 상태값 (visit CANCELED, 주석 처리됨)" \
     "INSERT INTO visit(party_size,status) VALUES(2,'CANCELED')" "Data truncated"
deny "State Diagram에 없는 상태값 (task DONE, 주석 처리됨)" \
     "$SETUP; INSERT INTO task(task_type,state,visit_id) VALUES('GUIDE','DONE',@v)" "Data truncated"
deny "장치 오류인데 오류 코드 없음 (SR-036)" \
     "INSERT INTO incident(source,robot_id) VALUES('DEVICE_ERROR','amr_1')" "chk_incident_error"
deny "AI 판단 값 오류 (익힘 판정에 NEAR)" \
     "$SETUP; INSERT INTO task(task_type,state,order_item_id) VALUES('COOK','COOK_TASK',@i1); INSERT INTO vision_result(task_id,robot_id,kind,decision) VALUES(LAST_INSERT_ID(),'arm_fry','DONENESS','NEAR')" "chk_vision_decision"

echo "■ 권한"
deny "team_dev는 테이블 구조 변경 불가" "DROP TABLE event_log" "DROP command denied"

echo
echo "결과: 통과 $PASS / 실패 $FAIL"
[ "$FAIL" -eq 0 ]
