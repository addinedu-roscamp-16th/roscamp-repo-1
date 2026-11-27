"""배터리 하한(min_battery)과 홈 복귀를 한 규칙으로(T-65).

[수정 2026-11-27] 신규. 모의 함대(MockFleet, ROS 없음)로 test_map_v06 에서
본다. 모의 로봇은 배터리를 늘 100 으로 보고하므로 FleetCore.on_robot_status 를
감싸 로봇별 배터리 값을 넣는다(값이 없으면 보고를 버려 오프라인을 흉내 냄).
"""
import os

os.environ['FRYBOT_MAP_ID'] = 'test_map_v06'

from frybot_control.mock_fleet import MockFleet  # noqa: E402
from frybot_control.mock_fleet import TimeModel  # noqa: E402


def _world(p1_node: str = 'B3') -> tuple[MockFleet, dict]:
    """pinky1 은 p1_node, pinky2 는 H2 에 세운 모의 관제와 배터리 표."""
    os.environ['FRYBOT_MAP_ID'] = 'test_map_v06'
    w = MockFleet(['pinky1', 'pinky2'], TimeModel('ideal', 0.08), dt=0.1,
                  pv_base=0, scheduler='min_cost_eta_rh', planner='sipp')
    batt = {'pinky1': 100.0, 'pinky2': 100.0}
    orig = w.core.on_robot_status

    def status(rid, x, y, yaw, battery, charging, state, error=''):
        if batt.get(rid) is None:
            return                      # 보고 끊김(오프라인)
        orig(rid, x, y, yaw, batt[rid], charging, state, error)
    w.core.on_robot_status = status
    w.place('pinky1', p1_node)
    w.place('pinky2', 'H2')
    for _ in range(5):
        w.step()
    return w, batt


def _run(w: MockFleet, seconds: float) -> None:
    """모의 시각을 seconds 만큼 돌린다."""
    end = w.t + seconds
    while w.t < end:
        w.step()


def _node(w: MockFleet, rid: str) -> str:
    """관제가 보는 로봇의 노드."""
    return w.core.robots[rid].node


def _logs(w: MockFleet, event: str) -> list:
    """모의 관제 기록 중 event 이름인 것."""
    return [e for e in w.events if e.get('event') == event]


def test_idle_robot_off_home_goes_home_when_low():
    """가) 홈 밖에 선 임무 없는 로봇이 20 % 면 스스로 홈(H1)으로."""
    w, batt = _world('B3')
    _run(w, 5.0)
    assert _node(w, 'pinky1') == 'B3'
    batt['pinky1'] = 20.0
    _run(w, 60.0)
    assert _node(w, 'pinky1') == 'H1'
    rh = [e for e in _logs(w, 'RETURN_HOME') if e.get('robot_id') == 'pinky1']
    assert rh and 'low_battery=20.0%' in rh[0].get('reason', '')


def test_low_during_task_finishes_then_home_and_no_new_task():
    """나) 이동 임무 중 20 % 로: 임무는 끝내고 홈으로, 그동안 새 임무 없음."""
    w, batt = _world('B3')
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'B1')
    assert ok, msg
    _run(w, 2.0)
    batt['pinky1'] = 20.0
    _run(w, 30.0)
    move = [t for t in w.core.tasks.values() if t.type == 'MOVE']
    assert move[0].state == 'DONE'
    # 하한 미만이라 새 이동 명령(홈이 아닌 곳)은 거절
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'B2')
    assert not ok and '배터리' in msg
    _run(w, 60.0)
    assert _node(w, 'pinky1') == 'H1'
    assert not w.core._available(w.core.robots['pinky1'])


def test_go_home_accepted_move_rejected_when_low():
    """다) 20 % 에서 GO_HOME 은 받고, 다른 노드 MOVE_TO_VERTEX 는 거절."""
    w, batt = _world('B3')
    batt['pinky1'] = 20.0
    for _ in range(3):
        w.step()
    ok, msg = w.core.command('MOVE_TO_VERTEX', 'pinky1', 'B2')
    assert not ok
    assert '배터리 20% < 25%' in msg and 'GO_HOME 은 가능' in msg
    rej = _logs(w, 'MOVE_REJECT')
    assert rej and 'GO_HOME 은 가능' in rej[-1].get('reason', '')
    # 자동 복귀가 시작되기 전(배터리만 하한 아래)에 받은 GO_HOME 도 받음
    w2, _ = _world('B3')
    w2.core.robots['pinky1'].battery = 20.0
    ok, msg = w2.core.command('GO_HOME', 'pinky1')
    assert ok, msg
    _run(w2, 60.0)
    assert _node(w2, 'pinky1') == 'H1'


def test_go_home_while_auto_returning_is_accepted():
    """자동 복귀 중에 GO_HOME 을 보내도 '경로 실행 중'으로 거절하지 않음."""
    w, batt = _world('B3')
    batt['pinky1'] = 20.0
    w.step()
    assert w.core.robots['pinky1'].returning
    ok, msg = w.core.command('GO_HOME', 'pinky1')
    assert ok and '복귀 중' in msg, msg


def test_no_auto_home_above_threshold():
    """라) 30 % 면 지금과 같음: 홈 밖에 그대로 섬."""
    w, batt = _world('B3')
    batt['pinky1'] = 30.0
    _run(w, 60.0)
    assert _node(w, 'pinky1') == 'B3'
    assert not [e for e in _logs(w, 'RETURN_HOME')
                if e.get('robot_id') == 'pinky1']


def test_estop_or_offline_robot_does_not_go_home():
    """마) 비상 정지·오프라인 로봇은 자동 복귀하지 않음."""
    w, batt = _world('B3')
    ok, msg = w.core.command('ESTOP', 'pinky1', 'test')
    assert ok, msg
    batt['pinky1'] = 20.0
    _run(w, 30.0)
    assert _node(w, 'pinky1') == 'B3' and not w.core.robots['pinky1'].route
    w2, batt2 = _world('B3')
    batt2['pinky1'] = None             # 보고가 끊김
    _run(w2, 5.0)
    assert not w2.core.robots['pinky1'].online
    w2.core.robots['pinky1'].battery = 20.0
    _run(w2, 30.0)
    assert not w2.core.robots['pinky1'].route
