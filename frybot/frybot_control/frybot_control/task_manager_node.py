"""Task Manager node (Main Server): wraps FleetCore with ROS 2 actions / topics / services."""
import json
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

from frybot_interfaces.action import ArmJob, NavigateRoute
from frybot_interfaces.msg import ArmStatus, FleetHeartbeat, RobotStatus, TaskEvent, TrafficGrant, Waypoint
from frybot_interfaces.srv import FleetCommand, SubmitTask

from .fleet_core import FleetCore, FleetIO
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from .map_catalog import require_map_id

QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


class TaskManager(Node, FleetIO):
    def __init__(self):
        super().__init__('task_manager')
        require_map_id('task_manager')
        p = self.declare_parameter
        # [수정 2026-11-18] P1: 노드 기본값을 실기기 값으로(robot_ids 는
        # real.launch.py 의 등록 없음 기본과 같은 pinky1, use_standby 끔,
        # auto_home 켬). 시뮬 런치가 예전 값을 명시함. FleetCore 기본값은
        # 그대로(오프라인 도구가 씀)
        self.robot_ids = p('robot_ids', ['pinky1']).value
        self.core = FleetCore(self, robot_ids=self.robot_ids, scheduler=p('scheduler', 'min_cost_eta_rh').value,
                              planner=p('planner', 'sipp').value, speed=p('speed', 0.08).value,
                              guide_speed=p('guide_speed', 0.05).value, cook_time_scale=p('cook_time_scale', 20.0).value,
                              stall_timeout=p('stall_timeout', 3.0).value, use_doneness=p('use_doneness', True).value,
                              use_standby=p('use_standby', False).value, prefer_yield=p('prefer_yield', True).value,
                              route_retries=p('route_retries', 2).value,
                              # [수정 2026-11-17] 기동 후 출발 노드 자동 이동
                              # (실측 지도에서만 동작)
                              # [수정 2026-11-18] P1: 기본 켬(실기기 값)
                              auto_home=p('auto_home', True).value,
                              # [수정 2026-11-18] W6: 계획의 구간 지연(초)
                              plan_overhead=p('plan_overhead', 0.0).value)
        self.session = f'{int(time.time()):x}'       # tells the robots when the Task Manager has been restarted
        self.nav = {r: ActionClient(self, NavigateRoute, f'/{r}/navigate_route') for r in self.robot_ids}
        # [수정 2026-11-17] SW 아키텍처 v016: 조리 팔 작업은 팔마다 따로 보내지
        # 않고 FrybotArm Master Controller(frybot_arm) 한 곳으로 보냄.
        # 서빙 팔은 전처럼 로봇마다 /<robot>/arm_job
        self.arm = {r: ActionClient(self, ArmJob, f'/{r}/arm_job')
                    for r in self.robot_ids}
        cook = ActionClient(self, ArmJob, '/frybot_arm/arm_job')
        self.arm.update({a: cook for a in ('cook_arm_a', 'cook_arm_b')})
        self.nav_goal = {}
        self.nav_sent, self.nav_void = {}, set()     # newest plan version sent per robot / goals canceled before acceptance
        self.arm_goal = {}
        self.pub_beat = self.create_publisher(FleetHeartbeat, '/fms/heartbeat', 10)
        self.pub_grant = self.create_publisher(TrafficGrant, '/fms/traffic_grant', QOS)
        self.pub_event = self.create_publisher(TaskEvent, '/fms/task_events', QOS)
        self.pub_state = self.create_publisher(String, '/fms/state', 10)
        self.pub_log = self.create_publisher(String, '/frybot/event_log', QOS)
        self.create_subscription(RobotStatus, '/fleet/robot_status', self._status, 50)
        self.create_subscription(String, '/ai/results', self._ai, 50)
        # [수정 2026-11-17] UR-17, 19: 로봇팔(조리 팔, 서빙 팔)의 상태·오류 보고
        self.create_subscription(
            ArmStatus, '/fleet/arm_status',
            lambda m: self.core.on_arm_status(
                m.arm_id, m.state, m.job, m.task_id, m.error), 20)
        self.create_service(SubmitTask, '/fms/submit_task', self._submit)
        self.create_service(FleetCommand, '/fms/command', self._command)
        self.create_timer(0.1, self._tick)
        self.create_timer(0.25, self._publish_state)
        self.create_timer(0.2, self._heartbeat)
        self.create_timer(0.5, self._regrant)
        self.get_logger().info(f'task manager up: scheduler={self.core.scheduler.name} planner={self.core.planner.name}')

    # ---------------------------------------------------------------- FleetIO
    def send_route(self, rid, task_id, pv, mode, visit_id, steps):
        g = NavigateRoute.Goal(task_id=task_id, robot_id=rid, plan_version=pv, mode=mode, visit_id=int(visit_id))
        for s in steps:
            x, y = self.core.graph.nodes[s.node]
            g.route.append(Waypoint(node_id=s.node, x=x, y=y, not_before=float(s.depart)))
        self.nav_sent[rid] = pv
        fut = self.nav[rid].send_goal_async(g, feedback_callback=lambda fb, rid=rid: self.core.on_route_progress(
            rid, fb.feedback.plan_version, fb.feedback.reached_index, fb.feedback.state))
        fut.add_done_callback(lambda f, rid=rid, pv=pv: self._nav_accepted(f, rid, pv))

    def _nav_accepted(self, fut, rid, pv):
        gh = fut.result()
        if not gh.accepted:
            self.nav_void.discard((rid, pv))
            self.core.on_route_result(rid, pv, False, 'REJECTED', -1)
            return
        if (rid, pv) in self.nav_void:               # canceled (e.g. emergency stop) before the robot accepted it
            self.nav_void.discard((rid, pv))
            gh.cancel_goal_async()
            return
        if self.nav_sent.get(rid) == pv:
            self.nav_goal[rid] = (pv, gh)
        gh.get_result_async().add_done_callback(lambda f, rid=rid: self._nav_result(f, rid))

    def _nav_result(self, fut, rid):
        r = fut.result().result
        self.core.on_route_result(rid, r.plan_version, r.success, r.reason, r.reached_index)

    def grant(self, rid, task_id, pv, index):
        self.pub_grant.publish(TrafficGrant(robot_id=rid, task_id=task_id, plan_version=pv, granted_index=index))

    def cancel_route(self, rid):
        pv, gh = self.nav_goal.pop(rid, (None, None))
        if gh is not None:
            gh.cancel_goal_async()
        sent = self.nav_sent.get(rid)
        if sent is not None and sent != pv:          # the newest goal has no handle yet: cancel it once it is accepted
            self.nav_void.add((rid, sent))

    def cancel_arm(self, arm_id):
        gh = self.arm_goal.pop(arm_id, None)
        if gh is not None:
            gh.cancel_goal_async()

    def _heartbeat(self):
        """Liveness + emergency-stop channel: robots stop when this goes silent, and hold while they are listed."""
        self.pub_beat.publish(FleetHeartbeat(stamp=self.get_clock().now().to_msg(), session=self.session,
                                             estop=self.core.estopped()))

    def _regrant(self):
        """Repeat the current permission of every active route (a lost message must not park a robot for ever)."""
        for rid, task_id, pv, index in self.core.active_grants():
            self.pub_grant.publish(TrafficGrant(robot_id=rid, task_id=task_id, plan_version=pv, granted_index=index))

    def arm_job(self, arm_id, task_id, job, duration, params):
        g = ArmJob.Goal(task_id=task_id, arm_id=arm_id, job=job, duration=float(duration), params_json=json.dumps(params))
        fut = self.arm[arm_id].send_goal_async(g)

        def accepted(f):
            gh = f.result()
            if not gh.accepted:
                self.core.on_arm_result(arm_id, task_id, False, 'REJECTED')
                return
            self.arm_goal[arm_id] = gh

            def done(f2):
                if self.arm_goal.get(arm_id) is gh:
                    del self.arm_goal[arm_id]
                r = f2.result().result
                self.core.on_arm_result(arm_id, task_id, r.success, r.reason or ('' if r.success else 'CANCELED'))
            gh.get_result_async().add_done_callback(done)
        fut.add_done_callback(accepted)

    def task_event(self, ev):
        m = TaskEvent(task_id=ev['task_id'], task_type=ev['task_type'], state=ev['state'], robot_id=ev['robot_id'],
                      visit_id=int(ev['visit_id']), order_id=int(ev['order_id']), item_id=int(ev['item_id']),
                      table_id=int(ev['table_id']), plan_version=int(ev['plan_version']), reason=str(ev.get('reason', '')))
        m.stamp = self.get_clock().now().to_msg()
        self.pub_event.publish(m)

    def log(self, event, **f):
        f.update(event=event, timestamp=time.time())
        self.pub_log.publish(String(data=json.dumps(f, ensure_ascii=False, default=str)))

    # ---------------------------------------------------------------- inputs
    def _status(self, m):
        self.core.on_robot_status(m.robot_id, m.x, m.y, m.yaw, m.battery, m.charging, m.state, m.error)

    def _ai(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        if d.get('kind') == 'DONENESS' and d.get('cook_task_id'):
            self.core.on_doneness(d['cook_task_id'], d['decision'], time.time())

    def _submit(self, req, res):
        try:
            res.task_id = self.core.submit_task(req.task_type, req.visit_id, req.order_id, req.item_id, req.table_id,
                                                req.menu, req.priority)
            res.accepted = True
        except Exception as e:  # noqa
            res.accepted, res.message = False, str(e)
        return res

    def _command(self, req, res):
        res.ok, res.message = self.core.command(req.command, req.target, req.arg)
        return res

    def _tick(self):
        self.core.tick(time.time())

    def _publish_state(self):
        self.pub_state.publish(String(data=json.dumps(self.core.snapshot(), ensure_ascii=False)))


def main():
    rclpy.init()
    n = TaskManager()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
