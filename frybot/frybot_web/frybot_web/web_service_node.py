"""Web Service (Main Server). Browsers talk HTTP; the service talks ROS 2 to Central Control and holds no state.

  /            index          /reception   입구 접수 태블릿
  /table?id=N  테이블 주문 태블릿   /admin       관리자 화면
"""
import csv
import glob
import hmac
import ipaddress
import json
import os
import threading

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

from frybot_control import layout
from frybot_control.map_catalog import (
    PROTO_LABEL, active_map_id, map_display, map_ids, profile)
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from frybot_control.map_catalog import require_map_id
from frybot_interfaces.srv import AdminCommand, CheckIn, EndUse, PlaceOrder

from .httpd import serve


# [수정 2026-11-17] UR-22: 이력의 처리 결과 분류 (이벤트 이름 / result 값)
_FAIL_EVENTS = ('TASK_SUSPEND', 'PLAN_FAIL', 'EVT_SUSPENDED', 'CHECKIN_REJECT',
                'ROUTE_RETRY', 'ESTOP', 'PAUSE', 'ALERT')
_OK_EVENTS = ('TASK_DONE', 'EVT_DONE', 'DELIVERED', 'ORDER_COMPLETED', 'SEATED',
              'TABLE_AVAILABLE', 'COOK_READY', 'EVT_READY', 'EVT_ARRIVED',
              'EVT_DELIVERED', 'EVT_RETURNED', 'CHECKIN', 'ORDER', 'END_USE',
              'HOME', 'RESUME')


def event_outcome(row: dict) -> str:
    """이벤트 한 줄의 처리 결과를 ok / fail / cancel / '' 로 나눈다.

    Args:
        row: events.csv 의 한 행.

    Returns:
        'cancel'(취소), 'fail'(실패·중단), 'ok'(성공·완료), 그 밖은 ''.
    """
    event, result = row.get('event', ''), row.get('result', '')
    if event == 'EVT_CANCELED' or result == 'CANCELED':
        return 'cancel'
    if event in _FAIL_EVENTS or result in ('FAIL', 'REJECTED'):
        return 'fail'
    if event in _OK_EVENTS or result == 'OK':
        return 'ok'
    return ''


class WebService(Node):
    def __init__(self):
        super().__init__('web_service')
        require_map_id('web_service')  # [수정 2026-11-18] P1(D1)
        port = self.declare_parameter('port', 8080).value
        # [수정 2026-11-17] D6: 관리자 명령(/api/admin)의 접근 통제.
        # admin_token: 값이 있으면 X-Admin-Token 헤더가 같아야 함
        # admin_local_only: 토큰이 없을 때 관제 PC(localhost)의 요청만 받음
        #   [수정 2026-11-18] P1: 기본을 실기기 값(True)으로 바꿈. 시뮬
        #   런치가 False 를 명시함(예전 기본 False)
        # 관제 PC 자신의 요청은 토큰 없이 받음
        self.admin_token = self.declare_parameter('admin_token', '').value
        self.admin_local_only = self.declare_parameter(
            'admin_local_only', True).value
        self.cli = {'check_in': self.create_client(CheckIn, '/frybot/check_in'),
                    'order': self.create_client(PlaceOrder, '/frybot/place_order'),
                    'end_use': self.create_client(EndUse, '/frybot/end_use'),
                    'admin': self.create_client(AdminCommand, '/frybot/admin')}
        self.rest, self.fms, self.world = {}, {}, {}
        self.create_subscription(String, '/frybot/state', lambda m: self._set('rest', m), 10)
        self.create_subscription(String, '/fms/state', lambda m: self._set('fms', m), 10)
        # [수정 2026-11-18] P3: 매장 시뮬 상태(/sim/world_state)는 sim_world 가
        # 참일 때만 구독(기본 False, 시뮬 런치가 켬)
        if self.declare_parameter('sim_world', False).value:
            self.create_subscription(
                String, '/sim/world_state',
                lambda m: self._set('world', m), 10)
        self.layout = layout.to_json()
        static = get_package_share_directory('frybot_web') + '/static'
        serve(port, static,
              get_routes={'/api/state': lambda q: {'rest': self.rest, 'fms': self.fms, 'world': self.world},
                          '/api/layout': lambda q: self.layout,
                          '/api/maps': self._maps,
                          '/api/map': self._map,
                          '/api/events': self._events},
              post_routes={'/api/checkin': self._checkin, '/api/order': self._order, '/api/end_use': self._end_use,
                           '/api/admin': self._admin},
              pages={'/': 'index.html', '/reception': 'reception.html', '/table': 'table.html', '/admin': 'admin.html'},
              post_guard=self._post_guard)
        self.get_logger().info(f'web service: http://localhost:{port}/')

    # [수정 2026-11-17] 지도 목록을 실행 종류에 맞춤. 실측 지도로 띄웠으면
    # maps/ 의 실측 지도 전부를 내어 한 화면에서 골라 볼 수 있게 하고 가상
    # 매장 도면(proto)은 빼며, proto 로 띄웠으면 proto 만 냄. 화면 쪽 약속대로
    # 가상 매장 도면의 id 는 빈 문자열
    def _maps(self, _query: dict) -> dict:
        """관리자 화면의 지도 목록을 돌려준다.

        Returns:
            active(관제가 쓰는 지도 id)와 maps(고를 수 있는 지도 목록).
        """
        active = active_map_id()
        if not active:
            return {'active': '', 'maps': [{'id': '', 'label': PROTO_LABEL}]}
        return {'active': active,
                'maps': [{'id': map_id, 'label': profile(map_id)['label']}
                         for map_id in map_ids()]}

    def _map(self, query: dict) -> dict:
        """실측 지도 하나의 그림과 노드를 돌려준다(실측 지도 실행에서만)."""
        map_id = query.get('id', '')
        if not active_map_id() or map_id not in map_ids():
            return {'ok': False, 'message': '고를 수 없는 지도입니다.'}
        return map_display(map_id)

    # [수정 2026-11-17] GUI 구성도 A3 "운영 이력 조회": 관리자 화면이 현재 실행의
    # 이벤트 기록(runs/<run_id>/events.csv)을 읽을 수 있게 함. 읽기 전용
    def _events(self, query: dict) -> dict:
        """현재 실행 폴더의 events.csv 에서 최근 이벤트를 돌려준다.

        Args:
            query: prefix(이 접두어로 시작하는 이벤트만, 쉼표 구분),
                skip(이 접두어로 시작하는 이벤트 제외), limit(최대 행 수,
                기본 300, 최대 2000), since / until(유닉스 초, 이 기간의
                이벤트만), result(ok | fail | cancel, 처리 결과).
                since 나 until 을 주면 실행 폴더(runs/)의 다른 실행 기록도
                함께 찾는다.

        Returns:
            ok, run_id, total(조건에 맞는 전체 행 수), events(최근 것이
            마지막인 행 목록). 기록 파일이 없으면 ok 가 False.
        """
        run_dir = self.rest.get('run_dir', '')
        path = os.path.join(run_dir, 'events.csv') if run_dir else ''
        if not path or not os.path.isfile(path):
            return {'ok': False, 'message': '실행 기록이 없습니다.',
                    'events': []}
        prefix = tuple(p for p in query.get('prefix', '').split(',') if p)
        skip = tuple(p for p in query.get('skip', '').split(',') if p)
        try:
            limit = max(1, min(int(query.get('limit', 300)), 2000))
        except ValueError:
            limit = 300
        # [수정 2026-11-17] UR-22: 기간(since, until)과 처리 결과(result) 필터.
        # 기간을 주면 같은 폴더의 다른 실행 기록도 읽음(기간 전에 끝난 것은 생략)
        since, until = _seconds(query.get('since')), _seconds(query.get('until'))
        result = query.get('result', '')
        paths = [path]
        if since is not None or until is not None:
            paths = sorted(
                p for p in glob.glob(
                    os.path.join(os.path.dirname(run_dir), '*', 'events.csv'))
                if since is None or os.path.getmtime(p) >= since)
        rows = []
        for name in paths:
            with open(name, newline='') as stream:
                for row in csv.DictReader(stream):
                    if prefix and not row['event'].startswith(prefix):
                        continue
                    if skip and row['event'].startswith(skip):
                        continue
                    stamp = _seconds(row.get('timestamp'))
                    if since is not None and (stamp is None or stamp < since):
                        continue
                    if until is not None and (stamp is None or stamp > until):
                        continue
                    if result and event_outcome(row) != result:
                        continue
                    rows.append(row)
        rows.sort(key=lambda row: _seconds(row.get('timestamp')) or 0.0)
        return {'ok': True, 'run_id': self.rest.get('run_id', ''),
                'runs': len(paths), 'total': len(rows), 'events': rows[-limit:]}

    # [수정 2026-11-17] 신규 (D6): 관리자 명령의 접근 통제
    def _post_guard(self, path: str, headers, client_ip: str) -> dict | None:
        """POST 요청을 받아도 되는지 판단한다.

        Args:
            path: 요청 경로.
            headers: 요청 헤더.
            client_ip: 요청을 보낸 주소.

        Returns:
            거부할 때 돌려줄 응답(need_token 이 참이면 화면이 토큰을 물음).
            받아도 되면 None.
        """
        if path != '/api/admin':
            return None
        try:
            if ipaddress.ip_address(client_ip).is_loopback:
                return None
        except ValueError:
            pass
        if self.admin_token:
            given = headers.get('X-Admin-Token', '')
            if hmac.compare_digest(given.encode(), self.admin_token.encode()):
                return None
            return {'ok': False, 'need_token': True,
                    'message': '관리자 토큰이 필요합니다.'}
        if self.admin_local_only:
            return {'ok': False, 'need_token': False,
                    'message': '관리자 명령은 관제 PC 에서만 보낼 수 있습니다 '
                               '(다른 기기는 admin_token 을 정해 실행).'}
        return None

    def _set(self, key, m):
        try:
            setattr(self, key, json.loads(m.data))
        except ValueError:
            pass

    def _call(self, name, req, timeout=4.0):
        c = self.cli[name]
        if not c.service_is_ready():
            raise RuntimeError('central control is not running')
        ev = threading.Event()
        fut = c.call_async(req)
        fut.add_done_callback(lambda f: ev.set())
        if not ev.wait(timeout):
            raise RuntimeError('central control did not answer')
        return fut.result()

    def _checkin(self, b):
        r = self._call('check_in', CheckIn.Request(party_size=int(b.get('party_size', 0))))
        return {'ok': r.accepted, 'visit_id': r.visit_id, 'table_id': r.table_id, 'message': r.message}

    def _order(self, b):
        items = [(i['menu'], int(i['qty'])) for i in b.get('items', []) if int(i.get('qty', 0)) > 0]
        r = self._call('order', PlaceOrder.Request(table_id=int(b['table_id']), menu_codes=[m for m, _ in items],
                                                   quantities=[q for _, q in items]))
        return {'ok': r.accepted, 'order_id': r.order_id, 'message': r.message}

    def _end_use(self, b):
        r = self._call('end_use', EndUse.Request(table_id=int(b['table_id']), source=b.get('source', 'TABLET')))
        return {'ok': r.accepted, 'message': r.message}

    def _admin(self, b):
        r = self._call('admin', AdminCommand.Request(command=b['command'], target=str(b.get('target', '')),
                                                     arg=str(b.get('arg', ''))))
        return {'ok': r.ok, 'message': r.message}


def _seconds(text) -> float | None:
    """문자열을 초(float)로 바꾼다. 비었거나 숫자가 아니면 None."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def main():
    rclpy.init()
    try:
        rclpy.spin(WebService())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
