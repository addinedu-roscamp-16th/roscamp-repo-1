"""Task Manager core (ROS-independent so it can also run in the offline benchmark).

Responsibilities
  * task queue + scheduler plug-in   -> which AMR takes which GUIDE / SERVE / COLLECT task
  * path planner plug-in             -> timed route on the single-lane roadmap
  * traffic layer                    -> node locks: request / grant / enter / exit, stall detection, replanning
  * cooking cell coordinator         -> cook arms A/B, fryer, wok, hand-off slots (acquire-all-at-once, no deadlock)

All side effects go through a FleetIO object; all inputs arrive via on_* methods and tick(now).
"""
import math
import random
import time
from dataclasses import dataclass, field

from . import device_state
from .layout import Graph, MENU, SAFE_DIST
from .planners import make_planner, PLANNERS, PlanRequest, ReservationTable, Step, INF, DEFAULT_PLANNER
from .schedulers import make_scheduler, SCHEDULERS, DEFAULT_SCHEDULER

AMR_TASKS = ('GUIDE', 'SERVE', 'COLLECT')
PRIORITY = {'GUIDE': 3, 'SERVE': 3, 'COLLECT': 1}
# [수정 2026-11-17] T-24: 우선순위를 뒤집힌 로봇이 되뒤집지 못하는 시간(초).
# 뒤집은 로봇이 두 구간쯤 갈 시간(실기기 구간당 약 3.5초)
FLIP_HOLD = 8.0
# [수정 2026-11-17] T-26: 비켜 준 유휴 로봇이 원래 노드로 돌아가려고 상대가
# 지나가기를 기다리는 최대 시간(초). 넘으면 비킨 자리에 남음
YIELD_BACK_WAIT = 60.0
# [수정 2026-11-18] W8-3: 같은 목적지 계획 실패가 이 시간(초)을 넘으면 임무를
# 보류하고 알림(임무가 없으면 알림만). mock_fleet 의 지표도 이 값을 씀
PLAN_FAIL_SUSPEND_SEC = 20.0


class FleetIO:
    """Outputs of the core. The ROS node and the offline simulator both implement this."""

    def send_route(self, robot_id, task_id, plan_version, mode, visit_id, steps): ...
    def grant(self, robot_id, task_id, plan_version, index): ...
    def cancel_route(self, robot_id): ...
    def cancel_arm(self, arm_id): ...
    def arm_job(self, arm_id, task_id, job, duration, params): ...
    def task_event(self, ev: dict): ...
    def log(self, event, **fields): ...


@dataclass
class Task:
    id: str
    type: str
    visit_id: int = 0
    order_id: int = 0
    item_id: int = 0
    table_id: int = 0
    menu: str = ''
    priority: int = 1
    created: float = 0.0
    state: str = 'PENDING'          # PENDING IN_PROGRESS DONE SUSPENDED CANCELED
    robot_id: str = ''
    phases: list = field(default_factory=list)
    pi: int = 0
    carrying: bool = False
    assigned_at: float = 0.0
    finished_at: float = 0.0
    reason: str = ''
    start_node: str = ''
    rebalanced: int = 0             # times the rolling-horizon scheduler moved it to another robot
    # [수정 2026-11-18] W2: State Diagram v4 의 LOADED -> SERVING. 적재 뒤
    # 테이블행 구간을 처음 나아갔을 때 SERVING 을 한 번만 내기 위한 표시
    serving_sent: bool = False


@dataclass
class Robot:
    id: str
    home: str
    node: str
    speed: float = 0.08
    heading: str = ''               # node we are driving to (locked), '' when standing on `node`
    route: list = None              # list[Step]
    idx: int = 0
    granted: int = 0
    plan_version: int = 0
    mode: str = 'NORMAL'
    goal: str = ''
    pending_goal: tuple = None      # (goal, mode, next_try)
    task: Task = None
    returning: bool = False
    arm_busy: str = ''
    arm_until: float = 0.0
    estop: bool = False
    battery: float = 100.0
    charging: bool = False
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    # [수정 2026-11-18] P2: 실기기 RobotStatus.state 를 담으므로 이름을 고침
    # (예전 sim_state)
    reported_state: str = ''
    wait_since: float = None
    blocked_by: str = ''
    last_replan: float = 0.0
    held: set = field(default_factory=set)
    dist: float = 0.0
    online: bool = False
    last_status: float = 0.0
    needs_replan: bool = False
    park: str = ''                  # where this robot waits when idle (charger or standby spot)
    yield_to: str = ''              # robot we stepped aside for; we resume only once it has passed
    yield_from: str = ''            # node we vacated for it
    yield_until: float = 0.0        # give up waiting for it after this time
    yield_note: str = ''            # robot we wait for on our own (short) path instead of driving a long way round
    last_yield: float = -1e9        # last time we stepped aside by choice (not twice within 10 s)
    error: str = ''                 # error the robot reports itself (device_state.ERROR name, '' = none)
    fail_count: int = 0             # failed routes in a row (reset by the next reached node)
    avoid_node: str = ''            # node the robot could not reach: plan round it until avoid_until
    avoid_until: float = 0.0
    # [수정 2026-11-17] T-23: 같은 판단을 다시 기록하지 않기 위한 표시
    wait_note: tuple = None
    skip_note: tuple = None
    # [수정 2026-11-17] T-24: 이 시각까지는 우선순위를 뒤집지 못함
    # (방금 뒤집은 상대를 되뒤집어 서로 계획을 무효화하는 것 방지)
    no_flip_until: float = 0.0
    # [수정 2026-11-17] 기동 후 출발 노드 자동 이동(auto_home)용 상태.
    # homed: 이번 관제 실행에서 자동 이동을 이미 처리함(성공·생략 모두)
    homed: bool = False
    still_pos: tuple = None         # 서 있다고 본 기준 위치
    still_since: float = 0.0        # 그 위치에 머문 시작 시각
    home_retry: float = 0.0         # 이 시각 전에는 다시 시도하지 않음
    home_note: str = ''             # 마지막으로 기록한 보류 이유
    # [수정 2026-11-17] UR-18: 관리자의 일시 중단(PAUSE). estop 과 함께 켜져
    # 로봇을 세우되, 화면에는 비상 정지가 아닌 "일시 중단"으로 표시
    paused: bool = False
    # [수정 2026-11-17] UR-19: 이상 종류 -> 시작 시각 (알람의 발생 시각)
    fault_since: dict = field(default_factory=dict)
    # [수정 2026-11-17] A3: 상태 보고가 끊긴 시각 (None = 연결됨)
    offline_since: float = None
    # [수정 2026-11-18] W8-3: 같은 목적지 계획 실패 묶음 [목적지, 첫 실패 시각,
    # 알림을 냈는지]. 계획이 성공하거나 목적지가 바뀌면 지움
    plan_fail: list = None


class CookJob:
    def __init__(self, task, ops):
        self.task, self.ops, self.pc = task, ops, 0
        self.busy = False            # an arm job / timer is running
        self.until = 0.0
        self.retries = 0
        self.wait_doneness_since = None
        self.label = 'QUEUED'


# [수정 2026-11-18] W2: 공정 단계 이름을 State Diagram v4 의 조리 작업 상태로
def _cook_state(job: CookJob) -> str:
    """조리 작업의 v4 상태를 돌려준다.

    Args:
        job: 조리 작업.

    Returns:
        WAIT_ARM(팔을 아직 잡지 못함), PROCESS(공정 수행 중),
        HANDOFF(인계대 배치 중), DONE, CANCELED 중 하나.
    """
    if job.task.state == 'CANCELED':
        return 'CANCELED'
    if job.task.state == 'DONE' or job.label == 'READY':
        return 'DONE'
    if job.label == 'QUEUED':
        return 'WAIT_ARM'
    if job.label == 'PLACE_HANDOFF':
        return 'HANDOFF'
    return 'PROCESS'


class FleetCore:
    def __init__(self, io: FleetIO, robot_ids=('pinky1', 'pinky2', 'pinky3'), scheduler=DEFAULT_SCHEDULER,
                 planner=DEFAULT_PLANNER, speed=0.08, guide_speed=0.05, cook_time_scale=20.0,
                 stall_timeout=3.0, min_battery=25.0, handoff_slots=3, use_doneness=True,
                 plan_speed_factor=0.9, use_standby=True, standby_min_battery=40.0, prefer_yield=True,
                 yield_detour_ratio=1.4, yield_detour_min=0.4, yield_max_wait=25.0, route_retries=2,
                 off_node_dist=0.06, rejoin_max_dist=1.0, pv_base=None,
                 auto_home=False, auto_home_settle=3.0, offline_hold=10.0,
                 plan_overhead=0.0, rng_seed=None):
        self.io = io
        # [수정 2026-11-17] A3: 로봇이 이 시간(초) 넘게 끊겨 있으면 진행 중인
        # 임무를 OFFLINE 으로 보류(관리자가 RETRY_TASK 로 재개)
        self.offline_hold = offline_hold
        self.graph = Graph()
        self.speed, self.guide_speed = speed, guide_speed
        self.cook_scale = cook_time_scale
        self.stall_timeout = stall_timeout
        self.min_battery = min_battery
        self.use_doneness = use_doneness
        self.plan_speed_factor = plan_speed_factor
        # [수정 2026-11-18] W6(E1, R5-4): 계획의 구간 지연(초). 구간 시간 =
        # 지연 + 거리 / (속도 x plan_speed_factor). 손님 안내 구간의 실측
        # 지연은 없어 같은 값을 씀(가정). 기본 0.0 = 예전과 같음
        self.plan_overhead = plan_overhead
        # [수정 2026-11-18] W8-1: 물러난 뒤 다시 시도하는 시각을 흩는 난수.
        # 전역 random 대신 관제 코어의 생성기(rng_seed=None 이면 매번 다름)
        self.rng = random.Random(rng_seed)
        self.use_standby, self.standby_min_battery = use_standby, standby_min_battery
        # Yielding: when the planner's answer to another robot on our path is a long way round (longer than
        # ratio x shortest and shortest + min metres), wait for it on the short path (at most yield_max_wait seconds
        # later than the detour), or back into a side spot until it has passed.
        self.prefer_yield, self.yield_detour_ratio = prefer_yield, yield_detour_ratio
        self.yield_detour_min, self.yield_max_wait = yield_detour_min, yield_max_wait
        self.route_retries = route_retries           # automatic re-plans after a route the robot could not drive
        self.off_node_dist, self.rejoin_max_dist = off_node_dist, rejoin_max_dist
        # [수정 2026-11-17] 실기기는 정확한 출발 위치에 놓고 시작할 수 없음.
        # auto_home 이면 위치가 잡힌 로봇을 출발 노드(homes)로 한 번 보냄.
        # auto_home_settle: 위치 보고가 이 시간(초) 동안 3 cm 안에 머문 뒤
        # 출발(AMCL 초기 자세가 들어온 직후의 위치 변동을 피함)
        self.auto_home, self.auto_home_settle = auto_home, auto_home_settle
        # Plan versions never repeat across restarts of the Task Manager (a robot may still hold permissions of the
        # previous session): start from the clock, 1024 versions per second of wall time, below 2^30.
        self.pv_base = ((int(time.time()) & 0xFFFFF) << 10) if pv_base is None else pv_base
        self.scheduler = make_scheduler(scheduler)
        self.scheduler.core = self
        self.planner = make_planner(planner)
        self.robots = {}
        self.locks = {}                      # node -> robot id
        for rid in robot_ids:                 # any number of AMRs: the home spots come from the layout
            home = self.graph.home_of(rid)
            r = Robot(rid, home, home, speed=speed, plan_version=self.pv_base)
            r.x, r.y = self.graph.nodes[home]
            r.park = home
            if not self.graph.map_id:
                r.held = {home}
                self.locks[home] = rid
            self.robots[rid] = r
        self.tasks = {}
        self.seq = 0
        # cooking cell
        self.cook_jobs = []
        self.res_owner = {'ARM_A': None, 'ARM_B': None, 'FRYER': None, 'WOK': None}
        self.slots = {'FRY_PICKUP': 0, 'WOK_PICKUP': 0}
        self.slot_cap = handoff_slots
        self.doneness = {}                   # cook task id -> (decision, stamp)
        # [수정 2026-11-17] UR-17, 19: 팔이 스스로 보고한 상태
        # (/fleet/arm_status). arm id -> dict(state, job, task_id, error, t)
        self.arm_reports = {}
        self.arm_fault_since = {}            # 조리 팔 id -> 이상 시작 시각
        self.m = dict(grants=0, blocked_wait=0.0, planned_wait=0.0, replans=0, retreats=0, plan_fail=0,
                      plan_calls=0, plan_ms=0.0, tasks_done=0, stalls=0, flips=0, joint_plans=0, joint_fail=0,
                      reassign=0, yields=0, rejoins=0, route_retries=0)
        self.now = 0.0
        # [수정 2026-11-17] T-23: 양보하지 않은 이유(기록용, 판단에는 쓰지 않음)
        self._yield_why = ''
        self._last_tick = None
        self._last_rebalance = 0.0

    # ------------------------------------------------------------------ algorithms (hot swap)
    def set_scheduler(self, name):
        self.scheduler = make_scheduler(name)
        self.scheduler.core = self
        self.io.log('SET_SCHEDULER', result=name)

    def set_planner(self, name):
        self.planner = make_planner(name)
        self.io.log('SET_PLANNER', result=name)
        for r in self.robots.values():        # re-plan running routes with the new algorithm
            if r.route and not r.estop:
                self._start_move(r, r.goal, r.mode, replan=True)

    # ------------------------------------------------------------------ task intake
    def submit_task(self, type, visit_id=0, order_id=0, item_id=0, table_id=0, menu='', priority=0):
        if self.graph.map_id:
            raise ValueError('Restaurant stations are not defined on this map')
        self.seq += 1
        t = Task(f'{type[0]}{self.seq:04d}', type, visit_id, order_id, item_id, table_id, menu,
                 priority or PRIORITY.get(type, 1), self.now)
        self.tasks[t.id] = t
        if type == 'COOK':
            t.state = 'IN_PROGRESS'
            self.cook_jobs.append(CookJob(t, self._recipe(menu)))
        else:
            t.phases = self._program(t)
            t.start_node = self.graph.resolve(t.phases[0][1])
        self.io.log('TASK_SUBMIT', task_id=t.id, visit_id=visit_id, order_id=order_id, result=type, reason=menu)
        return t.id

    def _program(self, t):
        tbl = f'T{t.table_id}:serve'                 # serving / collecting point(s) of the table
        if t.type == 'GUIDE':
            return [('move', 'ENTRANCE', 'NORMAL'), ('event', 'AT_START'), ('move', f'T{t.table_id}:guide', 'GUIDE'),
                    ('event', 'ARRIVED')]
        if t.type == 'SERVE':
            pickup = MENU[t.menu]['pickup']
            return [('move', pickup, 'NORMAL'), ('arm', 'LOAD', 3.0), ('event', 'LOADED'),
                    ('move', tbl, 'NORMAL'), ('arm', 'UNLOAD', 3.0), ('event', 'DELIVERED')]
        if t.type == 'COLLECT':
            return [('move', tbl, 'NORMAL'), ('arm', 'COLLECT_DISHES', 4.0), ('event', 'COLLECTED'),
                    ('move', 'DISH_RETURN', 'NORMAL'), ('arm', 'RETURN_DISHES', 3.0), ('event', 'RETURNED')]
        raise ValueError(t.type)

    # ------------------------------------------------------------------ main loop
    def tick(self, now):
        dt = 0.0 if self._last_tick is None else now - self._last_tick
        self._last_tick = self.now = now
        # [수정 2026-11-17] A3: 끊김 판정을 지도와 무관하게 함(전에는 실측
        # 지도에서만 해서 가상 매장 시뮬로는 이 경로를 볼 수 없었음). 끊긴
        # 로봇에는 새 허가·재계획·배정을 하지 않고, 오래 끊기면 임무를 보류.
        # 락은 시간으로 풀지 않음(로봇이 어디 있는지 모름)
        for robot in self.robots.values():
            if robot.online and now - robot.last_status > 2.0:
                robot.online, robot.offline_since = False, now
                self.io.log('ROBOT_OFFLINE', robot_id=robot.id,
                            zone_id=robot.node, result='FAIL',
                            task_id=robot.task.id if robot.task else '')
            task = robot.task
            if not robot.online and robot.offline_since is not None \
                    and now - robot.offline_since > self.offline_hold \
                    and task and task.state == 'IN_PROGRESS':
                self._suspend(task, 'OFFLINE')
        self._schedule()
        for r in self.robots.values():
            held_task = bool(r.task and r.task.state == 'SUSPENDED')
            if r.needs_replan and r.online and not held_task \
                    and not (r.pending_goal and not r.route and not self._yield_done(r)):
                r.needs_replan = False
                if (r.route or r.pending_goal) and not r.estop:
                    g, mode = (r.pending_goal[0], r.pending_goal[1]) if r.pending_goal else (r.goal, r.mode)
                    standing = not r.heading
                    # [수정 2026-11-17] T-26: 돌아가기를 포기한 로봇은 물러서지 않음
                    if not self._start_move(r, g, mode, replan=True, allow_flip=False) and standing \
                            and (r.task or not self.graph.map_id):
                        self._retreat(r, None, goal=g, mode=mode)
            self._drive(r, dt)
            if not self.graph.map_id and r.online and r.task is None and not r.route and not r.pending_goal and not r.estop and not r.heading:
                if r.node != r.home and r.battery < self.standby_min_battery:
                    self._go_home(r, force_home=True)          # standby robot running low: go and charge
                elif r.node != r.park and not r.arm_busy:
                    self._go_home(r)                           # left somewhere (e.g. after stepping aside): go and park
            # [수정 2026-11-17] 실측 지도: 기동 후 출발 노드로 자동 이동
            self._auto_home(r)
            # [수정 2026-11-17] UR-19: 이상이 시작된 시각 기록
            self._note_faults(r)
        self._cook_tick()

    # ------------------------------------------------------------------ scheduling
    # [수정 2026-11-17] G2: 로봇이나 서빙 팔이 오류를 보고 중이면 새 임무를
    # 주지 않음(전에는 DRIVE_ERROR 가 있어도 안내·서빙을 배정했음)
    def _available(self, r):
        return (r.online and not r.estop and r.task is None and not r.arm_busy and r.battery >= self.min_battery
                and not self._fault(r))

    # [수정 2026-11-17] 신규 (G2)
    def _fault(self, r: Robot) -> str:
        """로봇이 보고 중인 오류 이름을 돌려준다 ('' = 없음).

        로봇의 RobotStatus.error 를 먼저 보고, 없으면 서빙 팔의 마지막
        보고를 본다. 팔의 오류는 보고가 끊겨도 남고, 정상 보고가 와야
        풀린다.
        """
        if r.error:
            return r.error
        arm = self.arm_reports.get(r.id)
        return 'ARM_ERROR' if arm and arm['error'] else ''

    # [수정 2026-11-17] 신규 (G2): 관리자의 이동 명령은 자동 배정과 조건을
    # 나눔. 주행 실패(DRIVE_ERROR)는 다음 구간을 성공해야 풀리므로, 관리자가
    # 노드로 되돌리는 이동은 받음. 통신·위치·팔 오류는 받지 않음
    def _movable(self, r: Robot) -> bool:
        """관리자의 이동·홈 복귀 명령을 받을 수 있는 로봇인지."""
        arm = self.arm_reports.get(r.id)
        return (r.online and not r.estop and r.task is None
                and not r.arm_busy and r.battery >= self.min_battery
                and r.error in ('', 'DRIVE_ERROR')
                and not (arm and arm['error']))

    def _cost_fn(self):
        """Seconds until a robot can be at the task's first stop. ETA schedulers ask the path planner, so waiting for
        aisle reservations of other robots (and a busy pick-up point) is included."""
        cache = {}

        def static(r, t):
            src = r.heading or r.node
            cost = self.graph.shortest_dist(src, t.start_node) / self.speed
            # [수정 2026-11-18] W6: 최단 경로의 구간 수 x 구간 지연
            if self.plan_overhead:
                hops = len(self._shortest_path(src, t.start_node)) - 1
                cost += max(0, hops) * self.plan_overhead
            return cost

        def eta(r, t):
            k = (r.id, t.start_node)
            if k not in cache:
                # [수정 2026-11-18] W6: 구간 지연(overhead) 추가
                req = PlanRequest(r.id, r.heading or r.node, t.start_node, self.now, self.speed * self.plan_speed_factor,
                                  goal_hold=4.0, overhead=self.plan_overhead)
                steps = self.planner.plan(self.graph, req, self._table(r)) if self.planner.coordinated else None
                cache[k] = (steps[-1].arrive - self.now) if steps else static(r, t) * (1.0 if steps is None and not
                                                                                     self.planner.coordinated else 3.0)
            return cache[k]
        return eta if self.scheduler.uses_eta else static

    def _assign(self, t, r):
        t.robot_id, t.state, t.assigned_at, t.pi = r.id, 'IN_PROGRESS', self.now, 0
        r.task, r.returning = t, False
        self.io.log('TASK_ASSIGN', task_id=t.id, robot_id=r.id, visit_id=t.visit_id, order_id=t.order_id,
                    result=self.scheduler.name, reason=f'wait={self.now - t.created:.1f}')
        self._event(t, 'ASSIGNED')
        self._run_phase(r)

    def _schedule(self):
        pend = [t for t in self.tasks.values() if t.state == 'PENDING' and t.type in AMR_TASKS]
        free = [r for r in self.robots.values() if self._available(r)]
        cost = self._cost_fn()
        if self.scheduler.rebalance and self.now - self._last_rebalance >= self.scheduler.rebalance_period:
            self._last_rebalance = self.now
            # not started = still driving to the first stop (no guest picked up, nothing loaded)
            # A task may change hands at most twice, and not within 6 s of its last assignment: otherwise two robots
            # can keep handing the same task to each other (each turns round, which flips the ETA comparison again).
            open_ = [t for t in self.tasks.values() if t.state == 'IN_PROGRESS' and t.type in AMR_TASKS and t.pi == 0
                     and not t.carrying and not self.robots[t.robot_id].estop
                     # [수정 2026-11-17] A3, G2: 끊겼거나 오류를 보고 중인
                     # 로봇의 임무는 재배정 비교에 넣지 않음
                     and self.robots[t.robot_id].online
                     and not self._fault(self.robots[t.robot_id])
                     and t.rebalanced < 2 and self.now - t.assigned_at >= 6.0]
            if open_:
                robots = free + [self.robots[t.robot_id] for t in open_]
                # a robot that is released again plans from where it is now
                pairs = self.scheduler.assign(pend + open_, robots, cost, self.now)
                new = {t.id: r for t, r in pairs}
                if all(t.id in new for t in open_):
                    gain = sum(cost(self.robots[t.robot_id], t) - cost(new[t.id], t) for t in open_)
                    moved = [t for t in open_ if new[t.id].id != t.robot_id]
                    if moved and gain > self.scheduler.rebalance_gain:
                        for t in moved:
                            old = self.robots[t.robot_id]
                            old.task = None
                            t.robot_id, t.state = '', 'PENDING'
                            t.rebalanced += 1
                            self.m['reassign'] += 1
                            self.io.log('TASK_REBALANCE', task_id=t.id, robot_id=old.id, result=new[t.id].id,
                                        reason=f'gain={gain:.1f}')
                        for t in moved:
                            self._assign(t, new[t.id])
                        for o in robots:                       # released robots without a new task go and park
                            if o.task is None and not o.estop and all(o is not new[t.id] for t in moved):
                                if o.route and not o.returning:
                                    self._go_home(o)
                        pend = [t for t in self.tasks.values() if t.state == 'PENDING' and t.type in AMR_TASKS]
                        free = [r for r in self.robots.values() if self._available(r)]
                        cost = self._cost_fn()
        if not pend or not free:
            return
        for t, r in self.scheduler.assign(pend, free, cost, self.now):
            self._assign(t, r)

    # ------------------------------------------------------------------ task programs
    def _run_phase(self, r):
        t = r.task
        while t and t.state == 'IN_PROGRESS':
            if t.pi >= len(t.phases):
                t.state, t.finished_at = 'DONE', self.now
                self.m['tasks_done'] += 1
                self._event(t, 'DONE')
                self.io.log('TASK_DONE', task_id=t.id, robot_id=r.id, visit_id=t.visit_id, order_id=t.order_id,
                            result='OK', reason=f'dur={t.finished_at - t.created:.1f}')
                r.task = None
                self._go_home(r)
                return
            ph = t.phases[t.pi]
            if ph[0] == 'event':
                if ph[1] == 'LOADED':
                    t.carrying = True
                    self.slots[MENU[t.menu]['pickup']] = max(0, self.slots[MENU[t.menu]['pickup']] - 1)
                if ph[1] in ('DELIVERED', 'RETURNED'):
                    t.carrying = False
                if ph[1] == 'COLLECTED':
                    t.carrying = True
                self._event(t, ph[1])
                t.pi += 1
                continue
            if ph[0] == 'move':
                if len(self.graph.table_nodes.get(ph[1], ())) > 1:      # table reachable from several sides
                    ph = t.phases[t.pi] = ('move', self._table_side(r, ph[1]), ph[2])
                goal = self.graph.resolve(ph[1])
                self._rejoin(r)                   # not standing on a node: drive back onto the roadmap first
                if r.node == goal and not r.heading:
                    # Already standing on the goal. A route may still be active (e.g. the robot was on its way home
                    # and got this task while passing the node): drop it instead of planning a one-node route, whose
                    # arrival is never reported (progress only counts indices above the current one).
                    if r.route:
                        self._stop_route(r)
                    r.returning, r.pending_goal = False, None
                    t.pi += 1
                    continue
                self._start_move(r, goal, ph[2])
                return
            if ph[0] == 'arm':                    # only after the stop at the node is confirmed (no route active)
                r.arm_busy, r.arm_until = ph[1], self.now + ph[2]
                self.io.arm_job(r.id, t.id, ph[1], ph[2], {'table_id': t.table_id, 'menu': t.menu})
                self.io.log('ARM_START', task_id=t.id, robot_id=r.id, zone_id=r.node, result=ph[1])
                return

    def _table_side(self, r, table):
        """Service node of a table that can be approached from several sides: the nearest one for this robot, with a
        penalty when another robot stands on it / is heading for it. The choice is kept for the rest of the move."""
        src = r.heading or r.node

        def cost(n):
            busy = any(o.id != r.id and (o.goal == n and (o.route or o.pending_goal) or o.node == n)
                       for o in self.robots.values())
            return self.graph.shortest_dist(src, n) + (0.6 if busy else 0.0)
        return min(self.graph.table_nodes[table], key=cost)

    def _park_goal(self, r, force_home=False):
        """Where an idle robot waits. Chargers sit next to the entrance (guiding); the standby spots sit next to the
        cook zone (serving). Keep one robot on the entrance side, send the others to a free standby spot."""
        others = [o for o in self.robots.values() if o.id != r.id and not o.estop]
        if r.battery < self.standby_min_battery and r.home not in self.graph.home_nodes:
            # an AMR without its own charger borrows a free one (nobody parked on it or heading for it)
            used = {o.park for o in others} | {o.node for o in others}
            # [수정 2026-11-18] W8-1: 거리가 같을 때 집합 순서로 고르지
            # 않게 정렬
            free = [n for n in sorted(self.graph.home_nodes)
                    if n not in used and self._blocker(n, r.id) is None]
            if free:
                return min(free, key=lambda n: self.graph.shortest_dist(r.heading or r.node, n))
        if force_home or not self.use_standby or r.battery < self.standby_min_battery:
            return r.home
        entrance_side = sum(1 for o in others if o.task is None and (o.park or o.node) in self.graph.home_nodes)
        if entrance_side < 1:
            return r.home
        taken = {o.park for o in others if o.task is None} | {o.node for o in others if o.task is None}
        free = [n for n in self.graph.standby_nodes if n not in taken and self._blocker(n, r.id) is None]
        if not free:
            return r.home
        return min(free, key=lambda n: self.graph.shortest_dist(r.heading or r.node, n))

    # [수정 2026-11-17] 신규: 기동 후 출발 노드(대기 위치) 자동 이동
    def _auto_home(self, r: Robot) -> None:
        """위치가 잡힌 로봇을 자기 출발 노드로 한 번 보냄(실측 지도).

        로봇을 정확한 노드 위에 놓고 시작할 수 없으므로, 처음 온라인이 된
        로봇이 서 있는 곳에서 출발 노드(roadmap.json 의 homes)까지 이동
        명령(MOVE_TO_VERTEX)과 같은 경로로 보냄. 노드 밖에 있으면 가장
        가까운 빈 노드로 먼저 들어감(_rejoin). 로봇마다 관제 실행당 한 번만
        하고, 그 전에 운영자가 임무를 주거나 비상 정지를 걸면 하지 않음.

        Args:
            r: 대상 로봇.
        """
        if r.homed or not self.auto_home or not self.graph.map_id \
                or not r.online:
            return
        if r.task or r.estop:
            r.homed = True                 # 운영자가 먼저 개입: 맡김
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='SKIP',
                        reason='estop' if r.estop else 'operator task')
            return
        if r.route or r.pending_goal or self.now < r.home_retry \
                or self.now - r.still_since < self.auto_home_settle:
            return
        off = math.dist((r.x, r.y), self.graph.nodes[r.home])
        if off <= self.off_node_dist:
            r.homed = True
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='AT_HOME', reason=f'off={off:.2f}m')
            return
        ok, message = self._move_to_vertex(r.id, r.home)
        if ok:
            r.homed = True
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='OK', reason=message)
            return
        r.home_retry = self.now + 3.0      # 막혀 있으면 3초 뒤 다시 시도
        if message != r.home_note:
            r.home_note = message
            self.io.log('AUTO_HOME', robot_id=r.id, zone_id=r.home,
                        result='WAIT', reason=message)

    def _go_home(self, r, force_home=False):
        if self.graph.map_id:
            return
        goal = self._park_goal(r, force_home)
        r.park = goal
        if r.node == goal and not r.heading:
            return
        r.returning = True
        self._start_move(r, goal, 'NORMAL')

    def _event(self, t, state, reason=''):
        self.io.task_event(dict(task_id=t.id, task_type=t.type, state=state, robot_id=t.robot_id, visit_id=t.visit_id,
                                order_id=t.order_id, item_id=t.item_id, table_id=t.table_id,
                                plan_version=self.robots[t.robot_id].plan_version if t.robot_id in self.robots else 0,
                                reason=reason or t.reason))

    # ------------------------------------------------------------------ planning
    def _table(self, me, optimistic=False, exclude=()):
        """Reservations of all other robots. optimistic=True ignores their future plans (only what they occupy now):
        used when `me` cannot find a plan, so that `me` goes first and the others re-plan around it."""
        tb = ReservationTable(conflict=self.graph.conflict)
        for o in self.robots.values():
            if o.id == me.id or o.id in exclude:
                continue
            if optimistic and (o.route or o.pending_goal) and not o.estop:
                for n in o.held:
                    tb.add(n, self.now, self.now + 5.0, o.id)
                    tb.itineraries.append([(n, self.now), (n, self.now + 5.0)])
            elif o.route and self.planner.coordinated and o.route[0].arrive > 0:
                rem = o.route[max(o.idx, 0):]
                hold = self._hold_estimate(o, at_goal=True)
                tb.add_plan(o.id, rem, last_hold=hold)
                for n in o.held:                       # what it physically occupies right now
                    tb.add(n, self.now, self.now + 1.5, o.id)
                pts = [(rem[0].node, min(self.now, rem[0].depart))]
                for i, st in enumerate(rem):
                    if i:
                        pts.append((st.node, st.arrive))
                    pts.append((st.node, st.depart if i + 1 < len(rem) else st.arrive + hold))
                tb.itineraries.append(pts)
            else:
                hold = self._hold_estimate(o)
                for n in o.held:
                    tb.add(n, self.now, self.now + hold, o.id)
                    tb.itineraries.append([(n, self.now), (n, self.now + hold)])
        return tb

    def _hold_estimate(self, o, at_goal=False):
        if o.estop:
            return INF
        if at_goal:
            if o.returning:
                return INF
            t = o.task
            if t and t.pi + 1 < len(t.phases) and t.phases[t.pi + 1][0] == 'arm':
                return t.phases[t.pi + 1][2] + 2.0
            # [수정 2026-11-18] W8-2: 이동 명령(MOVE)처럼 지금 이동이 임무의
            # 마지막 단계면 도착 뒤 그 자리에 계속 섬. 4초 뒤 빈다고 예약하면
            # 뒤 로봇이 막다른 자리까지 들어와 둘 다 멈췄음(W5)
            if t and t.type == 'MOVE' and t.pi + 1 >= len(t.phases):
                return INF
            return 4.0
        if o.arm_busy:
            return max(1.0, o.arm_until - self.now) + 2.0
        if o.task is None and not o.route and not o.pending_goal:
            return INF                               # parked
        return 4.0

    def _start_move(self, r, goal, mode, replan=False, blocked=frozenset(), allow_flip=True):
        goal = self.graph.resolve(goal)
        self._rejoin(r)
        r.yield_note = ''
        self._yield_why = ''
        start = r.heading or r.node
        # plan a little slower than the robots drive, so small execution delays do not flip the planned order
        speed = (self.guide_speed if mode == 'GUIDE' else self.speed) * self.plan_speed_factor
        # [수정 2026-11-18] W6: 구간 중간이면 남은 시간을 (지연 + 거리 / 속도)의
        # 절반으로, 노드로 돌아가는 길도 한 구간(지연 포함)으로 봄
        ov = self.plan_overhead
        t0 = self.now
        if r.heading:
            seg = ov + self.graph.dist(r.node, r.heading) / speed
            t0 += seg * 0.5
        if r.heading and r.heading == r.node:        # driving back onto the roadmap from somewhere off it
            back = math.dist((r.x, r.y), self.graph.nodes[r.node])
            t0 += ov + back / speed
        hold = INF if (r.returning and goal == r.park) else 5.0
        req = PlanRequest(r.id, start, goal, t0, speed, goal_hold=hold,
                          blocked=blocked, overhead=ov)
        c0 = time.perf_counter()
        steps = None
        if self.planner.joint and allow_flip and not blocked:
            steps = self._plan_joint(r, req, goal, mode)
        if steps is None and not blocked and r.avoid_node and self.now < r.avoid_until \
                and r.avoid_node not in (goal, start):
            # the robot just failed to reach this node (obstacle, Nav2 gave up): look for a way round it first
            steps = self.planner.plan(self.graph, PlanRequest(r.id, start, goal, t0, speed, goal_hold=hold,
                                                              blocked=frozenset({r.avoid_node})), self._table(r))
        if steps is None:
            steps = self.planner.plan(self.graph, req, self._table(r))
        # [수정 2026-11-17] T-26: 비켜 준 뒤 원래 노드로 돌아가는 로봇(실측
        # 지도에서 임무 없이 움직이는 로봇)은 다른 로봇을 비키게 하거나
        # 우선순위를 뒤집지 않음. 그러면 서로 끝없이 자리를 바꿈
        quiet = bool(self.graph.map_id) and r.task is None and mode != 'YIELD'
        if self.prefer_yield and self.planner.coordinated and not blocked and mode != 'YIELD' and not quiet \
                and (steps is None or self._long_way(steps, start, goal)) and self._make_way(r, start, goal):
            # an idle robot stood in the way and is stepping aside now: plan again, the short way is opening up
            steps = self.planner.plan(self.graph, req, self._table(r)) or steps
        if steps is not None and self.prefer_yield and self.planner.coordinated and not self.planner.joint \
                and not blocked and not r.heading and mode != 'YIELD' and not quiet:
            alt = self._yield_instead(r, req, steps, goal, mode)
            if alt == 'RETREAT':                      # stepped aside; the move continues from the side spot
                self.m['plan_calls'] += 1
                self.m['plan_ms'] += (time.perf_counter() - c0) * 1000.0
                return True
            steps = alt or steps
        # [수정 2026-11-17] T-24: 마주 본 두 로봇이 1초마다 서로 뒤집어
        # 아무도 출발하지 못했음. 뒤집힌 쪽은 FLIP_HOLD 동안 되뒤집지 못함
        if steps is None and self.planner.coordinated and allow_flip \
                and not quiet and self.now >= r.no_flip_until:
            steps = self.planner.plan(
                self.graph, req, self._table(r, optimistic=True))
            # priority flip: the others must now plan around us
            if steps is not None:
                self.m['flips'] += 1
                for o in self.robots.values():
                    if o.id != r.id and (o.route or o.pending_goal) and not o.estop:
                        o.needs_replan = True
                        o.no_flip_until = self.now + FLIP_HOLD
        self.m['plan_calls'] += 1
        self.m['plan_ms'] += (time.perf_counter() - c0) * 1000.0
        r.goal, r.mode = goal, mode
        if steps is None and quiet:
            if r.heading and r.route:
                # 구간을 달리는 중: 허가받은 노드까지만 가서 다시 판단함.
                # 구간 중간에 서면 다른 로봇이 비켜 달라고 할 수 없음
                r.route = r.route[:max(r.granted, r.idx) + 1]
                r.pending_goal = (goal, mode, self.now + 1.0)
                return False
            # 돌아갈 길이 막혀 있음: 다시 시도하지 않고 지금 노드에 남음
            r.pending_goal = None
            r.yield_to = r.yield_from = ''
            self.io.log('YIELD_STAY', robot_id=r.id, zone_id=goal,
                        reason=f'no_way_back at={r.node}')
            self._stop_route(r)
            return False
        if steps is None:
            self.m['plan_fail'] += 1
            r.pending_goal = (goal, mode, self.now + 1.0)
            self.io.log('PLAN_FAIL', robot_id=r.id, task_id=r.task.id if r.task else '', zone_id=goal,
                        result=self.planner.name)
            if r.route:                               # keep standing where we are
                self._stop_route(r)
            self._plan_fail_watch(r, goal)
            return False
        # [수정 2026-11-18] W8-3: 계획 성공이면 실패 묶음을 지움
        r.plan_fail = None
        # [수정 2026-11-17] T-23: 계획에 든 대기와 양보하지 않은 이유를 기록
        self._log_plan_notes(r, steps, start, goal, mode, blocked)
        self._adopt(r, steps, goal, mode, replan)
        return True

    # [수정 2026-11-17] T-23: 실기기에서 양보처럼 보인 동작(계획 대기,
    # 우회)이 로그에 남지 않았음. 기록만 추가하고 판단은 바꾸지 않음
    def _user_of(self, r: Robot, nodes) -> str:
        """다른 로봇 중 `nodes`(와 너무 가까운 노드)를 쓰는 첫 로봇의 id.

        Args:
            r: 기준 로봇.
            nodes: 확인할 노드들.

        Returns:
            로봇 id. 없으면 ''.
        """
        region = set(nodes)
        for n in list(region):
            region |= self.graph.conflict[n]
        for o in self.robots.values():
            if o.id == r.id:
                continue
            used = set(o.held)
            if o.route:
                used |= {st.node for st in o.route[max(o.idx, 0):]}
            if used & region:
                return o.id
        return ''

    def _log_plan_notes(self, r: Robot, steps: list, start: str, goal: str,
                        mode: str, blocked: frozenset) -> None:
        """채택한 계획의 대기(PLAN_WAIT)와 우회 이유(YIELD_SKIP)를 기록함.

        Args:
            r: 계획을 받은 로봇.
            steps: 채택한 계획.
            start: 출발 노드.
            goal: 목적 노드.
            mode: 주행 모드.
            blocked: 계획에서 뺀 노드(조율하지 않는 재계획).
        """
        if len(steps) < 2 or mode == 'YIELD':
            return
        task_id = r.task.id if r.task else ''
        if self.planner.coordinated and steps[0].arrive > 0:
            waits = [(i, s.depart - s.arrive) for i, s in enumerate(steps[:-1])
                     if s.depart - s.arrive > 1.0]
            if waits:
                i, wait = waits[0]
                who = self._user_of(r, [steps[i + 1].node])
                key = (goal, steps[i].node, who)
                if key != r.wait_note:
                    r.wait_note = key
                    self.io.log(
                        'PLAN_WAIT', robot_id=r.id, task_id=task_id,
                        zone_id=steps[i].node,
                        reason=f'wait={wait:.1f}s for={who or "?"} '
                               f'next={steps[i + 1].node} '
                               f'total={sum(w for _, w in waits):.1f}s')
        short = self.graph.shortest_dist(start, goal)
        length = sum(self.graph.dist(a.node, b.node)
                     for a, b in zip(steps, steps[1:], strict=False)
                     if a.node != b.node)
        if length <= short + 0.05:
            return
        limit = max(short * self.yield_detour_ratio,
                    short + self.yield_detour_min)
        if blocked:
            why = 'uncoordinated_replan'
        elif not self.prefer_yield:
            why = 'prefer_yield_off'
        elif not self.planner.coordinated or self.planner.joint:
            why = 'planner_without_yield'
        elif length <= limit:
            why = 'below_threshold'
        elif r.heading:
            why = 'robot_between_nodes'
        else:
            why = self._yield_why or 'no_side_spot'
        who = self._user_of(r, self._shortest_path(start, goal))
        key = (goal, why, who)
        if key != r.skip_note:
            r.skip_note = key
            self.io.log(
                'YIELD_SKIP', robot_id=r.id, task_id=task_id, zone_id=goal,
                reason=f'{why} by={who or "?"} detour={length:.2f}m '
                       f'short={short:.2f}m limit={limit:.2f}m')

    # ------------------------------------------------------------------ exception handling: robot off the roadmap
    def _rejoin(self, r, avoid=()):
        """A standing robot that is not on a roadmap node (Nav2 gave up between two nodes, somebody moved it, the
        localisation jumped) gets the nearest free node as the start of its next route: `heading` is set to that
        node, so the route starts there, the robot drives to it first and only then asks for permissions.
        `avoid`: nodes not to pick (the node it just failed to reach). Returns True when a node was chosen."""
        if not r.online or r.route:
            return False
        pos = (r.x, r.y)
        pool = None
        if r.heading:
            if r.heading == r.node and r.node not in avoid:
                return False                              # already on its way back onto the roadmap
            if not avoid:
                return False                              # between two nodes: carry on to the one ahead (as before)
            pool = [n for n in (r.node, r.heading) if n not in avoid]
        elif math.dist(pos, self.graph.nodes[r.node]) <= self.off_node_dist:
            return False

        def free(nodes):
            return [n for n in nodes if n not in avoid and self._blocker(n, r.id) is None]
        cands = free(pool) if pool else []
        if not cands:
            cands = free(self.graph.nodes)
        if not cands:
            return False
        n = min(cands, key=lambda k: math.dist(pos, self.graph.nodes[k]))
        d = math.dist(pos, self.graph.nodes[n])
        if d > self.rejoin_max_dist:
            return False
        # keep the locks of nodes the body still overlaps; they are released when the robot reports the new node
        keep = {k for k in r.held if math.dist(pos, self.graph.nodes[k]) < SAFE_DIST}
        for k in r.held - keep - {n}:
            if self.locks.get(k) == r.id:
                del self.locks[k]
        r.held = keep | {n}
        self.locks[n] = r.id
        r.node = r.heading = n
        self.m['rejoins'] += 1
        self.io.log('REJOIN', robot_id=r.id, zone_id=n, task_id=r.task.id if r.task else '', reason=f'off_node={d:.2f}m')
        return True

    # ------------------------------------------------------------------ yielding instead of a long way round
    def _shortest_path(self, a, b):
        h = self.graph.sp_from(b)
        path = [a]
        while path[-1] != b and path[-1] in h and len(path) <= len(self.graph.nodes):
            path.append(min(self.graph.adj[path[-1]], key=lambda e: e[1] + h.get(e[0], 1e18))[0])
        return path

    def _long_way(self, steps, start, goal):
        """True when the plan is a long way round compared with the shortest path on the empty roadmap."""
        short = self.graph.shortest_dist(start, goal)
        length = sum(self.graph.dist(a.node, b.node) for a, b in zip(steps, steps[1:]) if a.node != b.node)
        return length > max(short * self.yield_detour_ratio, short + self.yield_detour_min)

    def _make_way(self, r, start, goal):
        """Idle robots parked on the shortest path of `r` (or too close to its goal) step aside into a side spot
        instead of making `r` drive a long way round, or wait for ever. Returns True when one started to move."""
        path = self._shortest_path(start, goal)
        region = set(path)
        for n in path:
            region |= self.graph.conflict[n]
        moved = False
        for o in self.robots.values():
            if o.id == r.id or not o.online or o.estop or o.task or o.route or o.pending_goal or o.arm_busy \
                    or o.heading or o.node not in region or self.now - o.last_yield < 10.0:
                continue
            # [수정 2026-11-17] T-26: 실측 지도에서는 비켜 준 로봇이 상대가
            # 지나간 뒤 서 있던 노드로 돌아감(운영자가 세워 둔 자리 유지).
            # 상대의 목적지가 그 노드이거나 너무 가까우면 돌아가지 않음
            target = self.graph.resolve(goal)
            back = bool(self.graph.map_id) and o.node not in (
                {target} | self.graph.conflict[target])
            if self._retreat(o, r, strict=True, clear=region, stay=True,
                             back=back):
                o.last_yield = self.now
                self.m['yields'] += 1
                moved = True
            # [수정 2026-11-17] T-24: 비킬 자리가 다른 유휴 로봇에 막혀 있으면
            # 그 로봇부터 비키게 함 (전에는 포기해 PLAN_FAIL 이 반복됨)
            elif self._clear_exit(o, r, region):
                moved = True
        return moved

    def _clear_exit(self, o: Robot, r: Robot, region: set) -> bool:
        """`o`가 `region` 밖으로 나갈 길을 막고 선 유휴 로봇을 비키게 함.

        Args:
            o: 비켜야 하지만 비킬 자리가 없는 유휴 로봇.
            r: 지나가려는 로봇.
            region: `r`이 지나갈 노드와 그에 너무 가까운 노드.

        Returns:
            비키기 시작한 로봇이 있으면 True.
        """
        def idle(q: Robot) -> bool:
            return bool(q.online and not (
                q.estop or q.task or q.route or q.pending_goal or q.arm_busy
                or q.heading) and self.now - q.last_yield >= 10.0)

        # 유휴 로봇이 선 노드는 지나갈 수 있다고 보고 가장 가까운 출구를 찾음
        prev, order, exit_node = {o.node: None}, [o.node], None
        for u in order:
            for n, _ in self.graph.adj[u]:
                if n in prev:
                    continue
                owner = self._blocker(n, o.id)
                if owner is not None and (
                        owner == r.id or not idle(self.robots[owner])):
                    continue
                prev[n] = u
                order.append(n)
                if n not in region:
                    exit_node = n
                    break
            if exit_node:
                break
        if exit_node is None:
            return False
        need, n = set(), exit_node
        while n is not None:
            need |= {n} | self.graph.conflict[n]
            n = prev[n]
        moved = False
        for q in self.robots.values():
            if q.id in (o.id, r.id) or not idle(q) or not q.held & need:
                continue
            if self._retreat(q, o, strict=True, clear=region | need,
                             stay=True):
                q.last_yield = self.now
                self.m['yields'] += 1
                moved = True
        return moved

    def _in_the_way(self, r, path):
        """The moving robot whose route (or body) meets `path` first, or None. Parked and stopped robots do not
        count: they will not move away, so driving round them is right."""
        best, at = None, len(path)
        index = {n: i for i, n in reversed(list(enumerate(path)))}
        for o in self.robots.values():
            if o.id == r.id or o.estop or not o.route:
                continue
            nodes = set(o.held) | {st.node for st in o.route[max(o.idx, 0):]}
            for n in list(nodes):
                nodes |= self.graph.conflict[n]
            hit = min((index[n] for n in nodes if n in index), default=None)
            if hit is not None and hit < at:
                best, at = o, hit
        return best

    def _yield_instead(self, r, req, steps, goal, mode):
        """`steps` avoids another robot. If that costs a long way round, give way instead: a plan that waits on the
        short path, or 'RETREAT' after backing into a side spot (the move then continues from there), else None."""
        if not self._long_way(steps, req.start, goal):
            return None
        short = self.graph.shortest_dist(req.start, goal)
        length = sum(self.graph.dist(a.node, b.node) for a, b in zip(steps, steps[1:]) if a.node != b.node)
        path = self._shortest_path(req.start, goal)
        o = self._in_the_way(r, path)
        # [수정 2026-11-17] T-23: 양보하지 않는 이유를 남김(기록용)
        if o is None:
            self._yield_why = 'no_moving_robot_on_path'
            return None
        loaded = lambda x, md: md == 'GUIDE' or bool(x.task and x.task.carrying)
        if loaded(r, mode) and not loaded(o, o.mode):
            self._yield_why = 'carrying'
            return None                               # guests in tow / food on board: keep moving, do not wait
        on = set(path)
        if self._stay_region(o) & on:
            self._yield_why = 'other_stops_on_path'
            return None                               # it will stop ON our short path: waiting cannot help, go round
        wait = self.planner.plan(self.graph, PlanRequest(
            # [수정 2026-11-18] W6: 구간 지연을 그대로 넘김
            r.id, req.start, goal, req.t0, req.speed,
            goal_hold=req.goal_hold, overhead=req.overhead,
            blocked=frozenset(n for n in self.graph.nodes if n not in on)), self._table(r))
        if wait is not None and all(s.node in on for s in wait) \
                and wait[-1].arrive - steps[-1].arrive <= self.yield_max_wait:
            self.m['yields'] += 1
            r.yield_note = o.id
            self.io.log('YIELD_WAIT', robot_id=r.id, zone_id=goal, task_id=r.task.id if r.task else '',
                        reason=f'yield_to={o.id} wait={wait[-1].arrive - steps[-1].arrive:+.1f}s '
                               f'instead_of_detour={length - short:+.2f}m')
            return wait
        if self.now - r.last_yield > 10.0 and self._retreat(r, o, goal=goal, mode=mode, strict=True):
            r.last_yield = self.now
            self.m['yields'] += 1
            return 'RETREAT'
        self._yield_why = 'wait_too_long_no_side_spot'
        return None

    def _stay_region(self, o):
        """Nodes robot `o` will occupy once its current move is over (its goal and the nodes too close to it)."""
        g = o.pending_goal[0] if o.pending_goal else (o.route[-1].node if o.route else o.node)
        return {g} | self.graph.conflict[g]

    def _reachable(self, src, dst, closed):
        seen, todo = {src}, [src]
        while todo:
            u = todo.pop()
            if u == dst:
                return True
            for n, _ in self.graph.adj[u]:
                if n not in seen and n not in closed:
                    seen.add(n)
                    todo.append(n)
        return False

    def _adopt(self, r, steps, goal, mode, replan=False):
        same_kind = r.goal == goal and r.mode == mode
        r.goal, r.mode, r.pending_goal = goal, mode, None
        if len(steps) == 1 and not r.heading and steps[0].node == r.node:
            # start == goal: nothing to drive, so no progress report would ever come. Treat it as arrived now.
            if r.route:
                self._stop_route(r)
            r.plan_version += 1
            self._arrived(r)
            return
        if replan and r.route and r.heading and same_kind and not r.yield_to and steps[0].arrive > 0:
            # The robot is between two nodes and the new plan visits the same nodes: only the timing changed. Keep the
            # route and its version and take over the new times. Re-sending it restarts the robot's current segment,
            # and a robot that is re-planned every few seconds (others keep changing plans) then never arrives.
            k = r.idx + 1
            if [s.node for s in r.route[k:]] == [s.node for s in steps]:
                for old, new in zip(r.route[k:], steps):
                    old.arrive, old.depart = new.arrive, new.depart
                return
        r.plan_version += 1
        r.route, r.idx, r.granted = steps, -1 if r.heading else 0, 0
        r.wait_since, r.blocked_by = None, ''
        self.io.send_route(r.id, r.task.id if r.task else 'RETURN', r.plan_version, mode,
                           r.task.visit_id if r.task else 0, steps)
        self.io.log('REPLAN' if replan else 'PLAN', robot_id=r.id, task_id=r.task.id if r.task else 'RETURN',
                    plan_version=r.plan_version, zone_id=goal, result=self.planner.name,
                    reason=f'len={len(steps)} eta={steps[-1].arrive - self.now:.1f}' if steps[-1].arrive else f'len={len(steps)}')

    def _request(self, o, goal, mode):
        speed = (self.guide_speed if mode == 'GUIDE' else self.speed) * self.plan_speed_factor
        # [수정 2026-11-18] W6: 구간 지연 포함(_start_move 와 같은 식)
        ov = self.plan_overhead
        t0 = self.now
        if o.heading:
            t0 += (ov + self.graph.dist(o.node, o.heading) / speed) * 0.5
        hold = INF if (o.returning and goal == o.park) else self._hold_estimate(o, at_goal=True)
        return PlanRequest(o.id, o.heading or o.node, goal, t0, speed,
                           goal_hold=hold, overhead=ov)

    def _plan_joint(self, r, req, goal, mode):
        """Joint planners (CCBS): plan `r` together with every other robot that is on its way somewhere."""
        others = [o for o in self.robots.values() if o.id != r.id and not o.estop and (o.route or o.pending_goal)]
        if not others:
            return None
        reqs = [req] + [self._request(o, o.pending_goal[0] if o.pending_goal else o.goal,
                                      o.pending_goal[1] if o.pending_goal else o.mode) for o in others]
        plans = self.planner.plan_joint(self.graph, reqs, self._table(r, exclude={o.id for o in others}))
        if plans is None:
            self.m['joint_fail'] += 1
            return None
        self.m['joint_plans'] += 1
        for o in others:
            g, md = (o.pending_goal[0], o.pending_goal[1]) if o.pending_goal else (o.goal, o.mode)
            old = [s.node for s in o.route[max(o.idx, 0):]] if o.route else None
            new = plans[o.id]
            if old == [s.node for s in new] and o.route and abs(new[-1].arrive - o.route[-1].arrive) < 1.0:
                continue                                   # unchanged: do not disturb the robot
            self._adopt(o, new, g, md, replan=True)
        return plans[r.id]

    def _stop_route(self, r):
        self.io.cancel_route(r.id)
        r.route = None

    # ------------------------------------------------------------------ traffic layer
    def _drive(self, r, dt):
        # [수정 2026-11-17] A3: 끊긴 로봇과 보류된 임무의 로봇에는 새 허가를
        # 내지 않고 보류한 이동도 시작하지 않음. 이미 낸 허가와 락은 그대로
        if r.estop or not r.online or (r.task and r.task.state == 'SUSPENDED'):
            return
        if r.pending_goal and self.now >= r.pending_goal[2] and self._yield_done(r):
            g, mode, _ = r.pending_goal
            self._start_move(r, g, mode, replan=True)
        if not r.route or r.idx < 0 or r.idx != r.granted:
            return
        if r.idx >= len(r.route) - 1:
            return
        timed = self.planner.coordinated and r.route[0].arrive > 0
        cur = r.route[r.idx]
        if timed:
            if self.now < cur.depart - 0.05:
                self.m['planned_wait'] += dt
                return
            late = self.now - cur.depart
            if late > 0.2:                                   # we are late: shift the rest of our plan
                for s in r.route[r.idx:]:
                    s.arrive += late if s is not cur else 0.0
                    s.depart += late
        nxt = r.route[r.idx + 1].node
        owner = self._blocker(nxt, r.id)
        if owner is None:
            self.locks[nxt] = r.id
            r.held.add(nxt)
            r.heading = nxt
            r.granted = r.idx + 1
            r.wait_since, r.blocked_by = None, ''
            self.m['grants'] += 1
            self.io.grant(r.id, r.task.id if r.task else 'RETURN', r.plan_version, r.granted)
            self.io.log('ZONE_GRANT', robot_id=r.id, zone_id=nxt, plan_version=r.plan_version,
                        task_id=r.task.id if r.task else 'RETURN')
            return
        # blocked by another robot's lock
        if r.wait_since is None:
            r.wait_since, r.blocked_by = self.now, owner
            self.io.log('ZONE_REQUEST', robot_id=r.id, zone_id=nxt, plan_version=r.plan_version, reason=f'held_by={owner}')
        self.m['blocked_wait'] += dt
        if self.now - r.wait_since > self.stall_timeout and self.now - r.last_replan > 2.0:
            self._resolve_stall(r, owner)

    def _blocker(self, node, rid):
        """Robot that prevents `rid` from entering `node` (holds it or a node too close to it), else None."""
        # [수정 2026-11-18] W8-1: 집합 순서(PYTHONHASHSEED)에 따라 막는 로봇이
        # 달라져 판단이 갈렸음. 정렬된 순서로 봄
        for n in (node, *sorted(self.graph.conflict[node])):
            o = self.locks.get(n)
            if o not in (None, rid):
                return o
        return None

    def _resolve_stall(self, r, owner):
        self.m['stalls'] += 1
        r.last_replan = self.now
        o = self.robots[owner]
        # [수정 2026-11-17] T-24: 상대가 이미 나에게 양보해 물러나는 중이면
        # 기다림. 전에는 나도 물러나 둘이 서로 30초씩 기다렸음
        # [수정 2026-11-17] A3: 단, 그 상대가 끊겼으면 기다리지 않음
        if o.yield_to == r.id and o.route and not o.estop and o.online:
            return
        mutual = o.blocked_by == r.id or o.pending_goal is not None or \
            (o.route and 0 <= o.idx and o.idx + 1 < len(o.route) and self._blocker(o.route[o.idx + 1].node, o.id) == r.id)
        # in a mutual block the lower-priority robot yields first; the other one waits one more round
        # [수정 2026-11-17] A3: 끊긴 상대는 비상 정지된 로봇처럼 비켜 주지
        # 못하는 것으로 봄
        stuck = o.estop or not o.online
        if mutual and not stuck and self._rank(r) > self._rank(o) and \
                self.now - r.wait_since < 2.5 * self.stall_timeout:
            return
        blocked = frozenset(n for x in self.robots.values() if x.id != r.id for n in x.held)
        self.m['replans'] += 1
        ok = self._start_move(r, r.goal, r.mode, replan=True,
                              blocked=blocked if not self.planner.coordinated else frozenset())
        if ok and r.route and len(r.route) > 1 and self._blocker(r.route[1].node, r.id) is None:
            return
        if mutual or stuck:
            self._retreat(r, o)

    def _yield_done(self, r):
        """After stepping aside for robot `o`, stay out of the way until `o` has passed the node we vacated (or finished,
        or 30 s went by). Resuming earlier puts us straight back in its way and the two keep swapping places."""
        if not r.yield_to:
            return True
        o = self.robots.get(r.yield_to)
        region = {r.yield_from} | self.graph.conflict.get(r.yield_from, set())
        ahead = {st.node for st in o.route[max(o.idx, 0):]} if o and o.route else set()
        passed = o is None or o.estop or (not o.route and not o.pending_goal) or \
            (o.route is not None and o.node not in region and o.heading not in region and not (ahead & region))
        # [수정 2026-11-17] T-26: 원래 노드로 돌아가려는 로봇(실측 지도, 임무
        # 없음)은 상대의 남은 길이 그 노드를 지나면 아직 지나간 것이 아님
        # (상대가 잠시 물러선 경우 포함). 기다리다 시간이 지나면 돌아가지
        # 않고 비킨 자리에 남음. 임무 중인 로봇 앞으로 되돌아가지 않기 위함
        if self.graph.map_id and r.task is None:
            if passed and o is not None and o.task and not o.estop:
                dest = o.pending_goal[0] if o.pending_goal else (
                    o.route[-1].node if o.route else '')
                if dest and set(self._shortest_path(
                        o.heading or o.node,
                        self.graph.resolve(dest))) & region:
                    passed = False
            if not passed and self.now > r.yield_until:
                self.io.log('YIELD_STAY', robot_id=r.id,
                            zone_id=r.yield_from,
                            reason=f'timeout wait_for={r.yield_to}')
                r.pending_goal = None
                r.yield_to = r.yield_from = ''
                return False
        if passed or self.now > r.yield_until:
            r.yield_to = r.yield_from = ''
            return True
        return False

    def _rank(self, r):
        p = r.task.priority if r.task else 0
        return (p + (1 if r.task and r.task.carrying else 0), -int(r.id[-1]) if r.id[-1].isdigit() else 0)

    def _retreat(self, r, o, goal=None, mode=None, strict=False, clear=(), stay=False, back=False):
        """Step aside so the other robot(s) can pass, then continue to the goal. Searches the free nodes around us and
        prefers a lay-by (비켜 서는 곳), then any node that is not on another robot's route.
        stay: an idle robot makes way (it has no goal of its own). back: with stay, it drives back to the node
        it vacated once the other robot has passed, instead of staying on the side spot."""
        # keep clear of the others' remaining routes AND of every node too close to them: a side spot next to the
        # aisle node the other robot needs (closer than SAFE_DIST) still blocks it, and the two would swap forever
        avoid = set()
        for x in self.robots.values():
            if x.id != r.id and x.route:
                for st in x.route[max(x.idx, 0):]:
                    avoid.add(st.node)
                    avoid |= self.graph.conflict[st.node]
        avoid |= set(clear)                               # nodes the other robot is about to plan through
        prev, order = {r.node: None}, [r.node]
        for u in order:                                   # BFS over nodes we could enter right now
            for n, _ in self.graph.adj[u]:
                if n not in prev and self._blocker(n, r.id) is None:
                    prev[n] = u
                    order.append(n)
        cands = order[1:]
        if strict:
            # By choice: only a spot that really clears the other's way, and from which our own goal can still be
            # reached once the other robot stands on ITS goal (a dead-end spur behind that goal would trap us).
            closed = self._stay_region(o) if o is not None and not stay else set()
            cands = [n for n in cands if n not in avoid and n not in closed
                     and (stay or self._reachable(n, self.graph.resolve(goal or r.goal), closed))]
            if not cands:
                return False
        if not cands:
            r.wait_since = self.now
            return False

        def depth(n):
            d = 0
            while prev[n] is not None:
                n, d = prev[n], d + 1
            return d
        # The aisles are one robot wide, so the robot backs out of the way instead of turning round: prefer spots whose
        # first step lies behind it (away from the robot it yields to), then the nearest, counting a lay-by / standby spot as two nodes closer.
        pull_in = self.graph.bay_nodes | set(self.graph.standby_nodes)
        hx, hy = math.cos(r.yaw), math.sin(r.yaw)
        if o is not None:                                 # facing unknown / sideways: "behind" = away from the other robot
            ox, oy = o.x - r.x, o.y - r.y
            if ox * hx + oy * hy <= 0.0 and math.hypot(ox, oy) > 1e-6:
                d = math.hypot(ox, oy)
                hx, hy = ox / d, oy / d
        x0, y0 = self.graph.nodes[r.node]

        def behind(n):
            first = n
            while prev[first] is not None and prev[first] != r.node:
                first = prev[first]
            fx, fy = self.graph.nodes[first]
            return (fx - x0) * hx + (fy - y0) * hy < 0.0
        # a lay-by / standby spot is worth two extra nodes of backing up, no more: long reverse runs block the aisle
        if strict:      # by choice: the nearest spot that clears the way (a side spot counts one node closer)
            cands.sort(key=lambda n: (depth(n) + (0 if n in pull_in else 1), not behind(n), depth(n)))
        else:
            cands.sort(key=lambda n: (n in avoid, not behind(n), depth(n) + (0 if n in pull_in else 2), depth(n)))
        side = cands[0]
        path = [side]
        while prev[path[-1]] is not None:
            path.append(prev[path[-1]])
        path.reverse()
        goal, mode = goal or r.goal, mode or r.mode
        if r.route:
            self.io.cancel_route(r.id)
        self.m['retreats'] += 1
        r.plan_version += 1
        timed = self.planner.coordinated
        t, steps = self.now, []
        for a, b in zip(path, path[1:] + [None]):
            # [수정 2026-11-18] W6: 물러나는 구간에도 구간 지연 포함
            dt = (self.plan_overhead + self.graph.dist(a, b) / self.speed
                  if b else 4.0)
            steps.append(Step(a, t if timed else 0.0, t if timed else 0.0))
            t += dt
        if timed:
            steps[-1].depart = t
        r.route, r.idx, r.granted = steps, 0, 0
        r.wait_since, r.blocked_by = None, ''
        # [수정 2026-11-17] T-26: 비켜 준 유휴 로봇이 원래 노드로 돌아감.
        # 임무 중 양보와 같은 방식(pending_goal, 상대가 지나갈 때까지 대기)
        if stay and back and o is not None:
            r.pending_goal = (path[0], 'NORMAL', t + self.rng.uniform(0.0, 3.0))
            r.returning, r.mode = False, 'YIELD'
            r.yield_to, r.yield_from = o.id, path[0]
            r.yield_until = t + YIELD_BACK_WAIT
            r.yield_note = o.id
        elif stay:                                        # idle robot making way: the side spot is where it stays
            r.pending_goal, r.returning, r.mode = None, False, 'YIELD'
            r.yield_to = r.yield_from = ''
            r.yield_note = o.id if o else ''
        else:
            r.pending_goal = (goal, mode, t + self.rng.uniform(0.0, 3.0))
            r.yield_to, r.yield_from, r.yield_until = (o.id if o else ''), r.node, t + 30.0
        r.goal = side
        self.io.send_route(r.id, r.task.id if r.task else 'RETURN', r.plan_version, 'YIELD', 0, r.route)
        self.io.log('RETREAT', robot_id=r.id, zone_id=side, plan_version=r.plan_version,
                    reason=f'yield_to={o.id if o else "plan"}' + (' idle_makes_way' if stay else ' by_choice' if strict else '')
                    + (f' back_to={path[0]}' if stay and back and o is not None else ''))
        return True

    # ------------------------------------------------------------------ inputs from robots
    def on_robot_status(self, rid, x, y, yaw, battery, charging, state, error=''):
        r = self.robots.get(rid)
        if not r:
            return
        # [수정 2026-11-17] G2: 'NO_ERROR' 도 오류 없음으로 봄
        r.last_status = self.now
        r.error = '' if error == 'NO_ERROR' else error
        # [수정 2026-11-17] A3: 다시 연결됨
        if not r.online and r.offline_since is not None:
            self.io.log('ROBOT_ONLINE', robot_id=rid, result='OK',
                        reason=f'offline={self.now - r.offline_since:.1f}s')
        r.offline_since = None
        # [수정 2026-11-17] auto_home: 3 cm 넘게 움직였거나 방금 연결됐으면
        # "서 있는 시간"을 다시 셈
        if not r.online or r.still_pos is None \
                or math.dist((x, y), r.still_pos) > 0.03:
            r.still_pos, r.still_since = (x, y), self.now
        if r.online:
            r.dist += math.hypot(x - r.x, y - r.y)
        r.x, r.y, r.yaw, r.battery, r.charging, r.reported_state, r.online = x, y, yaw, battery, charging, state, True
        if self.graph.map_id and state == 'IDLE' and not (r.route or r.pending_goal or r.task):
            vertex = self.graph.nearest_node(x, y)
            if self.locks.get(vertex) in (None, rid):
                self._claim_vertex(r, vertex)

    def _claim_vertex(self, robot, node):
        for previous in robot.held:
            if self.locks.get(previous) == robot.id:
                del self.locks[previous]
        robot.node, robot.held = node, {node}
        self.locks[node] = robot.id

    def on_route_progress(self, rid, plan_version, reached, state=''):
        r = self.robots.get(rid)
        if not r or not r.route or plan_version != r.plan_version or reached <= r.idx:
            return
        reached = min(reached, len(r.route) - 1)
        if reached > 0:
            r.fail_count = 0                                  # a segment was driven: earlier failures are history
        r.idx = reached
        r.node = r.route[reached].node
        r.heading = ''
        for n in list(r.held):
            if n != r.node:
                r.held.discard(n)
                if self.locks.get(n) == r.id:
                    del self.locks[n]
                self.io.log('ZONE_EXIT', robot_id=r.id, zone_id=n, plan_version=r.plan_version)
        r.held.add(r.node)
        self.locks[r.node] = r.id
        self.io.log('ZONE_ENTER', robot_id=r.id, zone_id=r.node, plan_version=r.plan_version)
        # [수정 2026-11-18] W2: 음식을 실은 서빙 임무가 테이블행 경로에서 한
        # 구간을 실제로 나아가면 SERVING(v4: 테이블 이동 시작). 비켜서기 중은 제외
        t = r.task
        if (t and t.type == 'SERVE' and t.carrying and not t.serving_sent
                and t.state == 'IN_PROGRESS' and not r.pending_goal):
            t.serving_sent = True
            self._event(t, 'SERVING')
        if reached == len(r.route) - 1:
            self._arrived(r)

    def on_route_result(self, rid, plan_version, success, reason, reached):
        r = self.robots.get(rid)
        if not r or plan_version != r.plan_version:
            return                                            # late result of an old plan: ignore
        if success:
            if r.route:
                self.on_route_progress(rid, plan_version, len(r.route) - 1)
            return
        if reason in ('PREEMPTED', 'CANCELED'):
            return
        r.route = None
        if r.estop:
            return                                            # stopped by the operator: the task is already suspended
        if reason in ('NAV2_FAILED', 'REJECTED', 'FMS_RESTART', 'E_STOP') and r.fail_count < self.route_retries:
            # Exception handling: the robot stands somewhere between two nodes. Take it back onto the roadmap (the
            # node behind it first) and plan again, round the node it could not reach while there is another way.
            r.fail_count += 1
            self.m['route_retries'] += 1
            goal, mode = (r.pending_goal[0], r.pending_goal[1]) if r.pending_goal else (r.goal, r.mode)
            failed = r.heading if r.heading != r.node else ''
            if reason == 'NAV2_FAILED' and failed:
                r.avoid_node, r.avoid_until = failed, self.now + 60.0
                self._rejoin(r, avoid={failed})
            r.pending_goal = (goal, mode, self.now + 1.5)
            self.io.log('ROUTE_RETRY', robot_id=r.id, task_id=r.task.id if r.task else '', zone_id=goal,
                        plan_version=plan_version, reason=f'{reason} try={r.fail_count}/{self.route_retries}')
            return
        r.pending_goal = None
        if r.task and r.task.state == 'IN_PROGRESS':
            self._suspend(r.task, reason)

    def _arrived(self, r):
        r.route, r.yield_note = None, ''
        if r.pending_goal:                                    # we only stepped aside; continue later
            return
        if r.returning:
            r.returning = False
            self.io.log('HOME', robot_id=r.id, zone_id=r.node)
            return
        if r.task and r.task.state == 'IN_PROGRESS':
            ph = r.task.phases[r.task.pi]
            if ph[0] == 'move' and self.graph.resolve(ph[1]) == r.node:
                r.task.pi += 1
            self._run_phase(r)

    def on_arm_result(self, arm_id, task_id, success, reason=''):
        if arm_id in self.robots:
            r = self.robots[arm_id]
            self.io.log('ARM_DONE', task_id=task_id, robot_id=arm_id, zone_id=r.node, result='OK' if success else 'FAIL',
                        reason=reason)
            r.arm_busy = ''
            t = r.task
            if not t or t.id != task_id or t.state != 'IN_PROGRESS':
                return
            if not success:
                self._suspend(t, reason or 'ARM_FAIL')
                return
            t.pi += 1
            self._run_phase(r)
            return
        for j in self.cook_jobs:                              # cooking arms
            if j.task.id == task_id and j.busy:
                j.busy = False
                if not success:
                    j.task.state, j.task.reason = 'SUSPENDED', reason or 'ARM_FAIL'
                    self._event(j.task, 'SUSPENDED', j.task.reason)
                else:
                    j.pc += 1

    # [수정 2026-11-17] 신규 (UR-17, 19): 팔의 상태·오류 보고 수신
    def on_arm_status(self, arm_id: str, state: str, job: str = '',
                      task_id: str = '', error: str = '') -> None:
        """팔 한 대가 보고한 상태를 저장한다 (/fleet/arm_status).

        Args:
            arm_id: 조리 팔 id(cook_arm_a, cook_arm_b) 또는 서빙 팔이 붙은
                로봇 id.
            state: device_state.STATE 이름.
            job: 수행 중인 팔 작업 이름 ('' = 없음).
            task_id: 그 작업의 임무 id.
            error: device_state.ERROR 이름 ('' = 이상 없음).
        """
        if error and error not in device_state.ERROR:
            error = 'UNCLASSIFIED_ERROR'
        if error == 'NO_ERROR':
            error = ''
        self.arm_reports[arm_id] = dict(
            state=state if state in device_state.STATE else 'UNKNOWN',
            job=job, task_id=task_id, error=error, t=self.now)

    def _arm_report(self, arm_id: str) -> dict | None:
        """최근 3초 안에 받은 팔 보고. 없거나 끊겼으면 None."""
        rep = self.arm_reports.get(arm_id)
        return rep if rep and self.now - rep['t'] <= 3.0 else None

    def _cook_arm_device(self, arm_id: str, letter: str) -> dict:
        """조리 팔의 기기 상태(화면용). 팔이 보고한 오류가 있으면 그것을,
        보고가 끊겼으면 OFFLINE 을, 보고를 받은 적이 없으면 관제가 시킨
        작업으로 추정한 상태를 돌려준다."""
        if arm_id in self.arm_reports:
            rep = self._arm_report(arm_id)
            if rep is None:
                out = device_state.report('OFFLINE', 'COMMUNICATION_ERROR')
            elif rep['error']:
                out = device_state.report('FAULT_HANDLING', rep['error'])
            else:
                out = device_state.arm_state(self._arm_job_of(letter))
            if out['error'] not in ('', 'NO_ERROR'):
                out['since'] = self.arm_fault_since.setdefault(
                    arm_id, self.now)
            else:
                self.arm_fault_since.pop(arm_id, None)
            return out
        return device_state.arm_state(self._arm_job_of(letter))

    def _serving_arm(self, r: Robot) -> dict:
        """AMR 에 붙은 서빙 팔의 상태(화면용)."""
        rep = self._arm_report(r.id)
        if rep:
            return dict(state=rep['state'], job=rep['job'],
                        error=rep['error'], reported=True)
        return dict(state='ARM_OPERATING' if r.arm_busy else 'IDLE',
                    job=r.arm_busy, error='', reported=False)

    def _note_faults(self, r: Robot) -> None:
        """이상 종류별로 시작 시각을 적어 둔다 (알람의 발생 시각)."""
        arm = self._arm_report(r.id)
        active = {
            'OFFLINE': not r.online,
            'E_STOP': r.estop and not r.paused,
            'PAUSED': r.paused,
            'ERROR': bool(r.error) and not r.estop,
            'LOW_BATTERY': r.online and r.battery < 20 and not r.charging,
            'OFF_NODE': self._off_node(r),
            'ARM_ERROR': bool(arm and arm['error']),
        }
        for kind, on in active.items():
            if on:
                r.fault_since.setdefault(kind, self.now)
            else:
                r.fault_since.pop(kind, None)

    def _unavailable_reason(self, r: Robot) -> str:
        """새 임무를 줄 수 없는 이유 ('' = 줄 수 있음). _available 과 같은
        조건을 같은 순서로 본다."""
        if not r.online:
            return 'OFFLINE'
        if r.paused:
            return 'PAUSED'
        if r.estop:
            return 'E_STOP'
        # [수정 2026-11-17] G2
        if self._fault(r):
            return 'ERROR'
        if r.task is not None:
            return 'ON_TASK'
        if r.arm_busy:
            return 'ARM_BUSY'
        if r.battery < self.min_battery:
            return 'LOW_BATTERY'
        return ''

    def on_doneness(self, task_id, decision, stamp):
        self.doneness[task_id] = (decision, stamp)

    # [수정 2026-11-18] W8-3: 계획 실패가 끝없이 반복돼도 보류·알림이 없었음
    # (W5에서 1,380초 반복)
    def _plan_fail_watch(self, r: Robot, goal: str) -> None:
        """같은 목적지 계획 실패가 20초를 넘으면 임무를 보류하고 알림.

        보류는 로봇 끊김(A3)과 같이 다시 시도 예정과 락을 그대로 두고,
        RETRY_TASK 로 재개함. 임무가 없으면 묶음마다 알림만 한 번 남기고
        다시 시도를 계속함.

        Args:
            r: 계획에 실패한 로봇.
            goal: 실패한 목적지.
        """
        pf = r.plan_fail
        if pf is None or pf[0] != goal:
            r.plan_fail = [goal, self.now, False]
            return
        if pf[2] or self.now - pf[1] <= PLAN_FAIL_SUSPEND_SEC:
            return
        pf[2] = True
        waited = f'goal={goal} for={self.now - pf[1]:.0f}s'
        if r.task and r.task.state == 'IN_PROGRESS':
            self._suspend(r.task, 'PLAN_FAIL')
            self.io.log('PLAN_FAIL_SUSPEND', robot_id=r.id, task_id=r.task.id,
                        zone_id=goal, result='FAIL', reason=waited)
        else:
            self.io.log('PLAN_FAIL_ALERT', robot_id=r.id, zone_id=goal,
                        result='FAIL', reason=waited)

    def _suspend(self, t, reason):
        t.state, t.reason = 'SUSPENDED', reason
        self.io.log('TASK_SUSPEND', task_id=t.id, robot_id=t.robot_id, visit_id=t.visit_id, order_id=t.order_id,
                    result='FAIL', reason=reason)
        self._event(t, 'SUSPENDED', reason)

    def _move_to_vertex(self, robot_id, destination):
        if not self.graph.map_id or destination not in self.graph.nodes or robot_id not in self.robots:
            return False, '지도, 로봇 또는 주행 노드를 확인하세요.'
        robot = self.robots[robot_id]
        # [수정 2026-11-18] W8-2: 다른 로봇이 같은 목적지나 너무 가까운 노드로
        # 가는 중이면 거절(서 있는 임무 없는 로봇은 비켜 주기가 처리)
        other = self._heading_near(destination, robot_id)
        if other:
            return False, (f'{other}이(가) {destination} 또는 바로 옆 노드로 '
                           '가는 중입니다. 도착한 뒤 다시 명령하세요.')
        old = robot.task
        if old and old.type == 'MOVE' and old.state == 'SUSPENDED' and not robot.estop:
            old.state = 'CANCELED'                       # a new move order replaces the one that got stuck
            self._event(old, 'CANCELED', 'replaced')
            robot.task = None
        # [수정 2026-11-17] T-26: 비켜 준 뒤 원래 노드로 돌아가려고 기다리는
        # 로봇(임무 없이 pending_goal 만 있음)도 새 이동 명령을 받음. 새
        # 명령이 복귀를 대신함
        if robot.pending_goal and not robot.task and not robot.route \
                and robot.online and not robot.estop:
            robot.pending_goal = None
            robot.yield_to = robot.yield_from = ''
        if robot.mode == 'YIELD' and robot.route and not robot.task \
                and robot.online and not robot.estop:
            # the robot is stepping aside for another one right now: take the order and start it from the side spot
            self.seq += 1
            task = Task(f'M{self.seq:04d}', 'MOVE', created=self.now, start_node=destination,
                        phases=[('move', destination, 'NORMAL')])
            self.tasks[task.id] = task
            task.robot_id, task.state, task.assigned_at = robot.id, 'IN_PROGRESS', self.now
            robot.task = task
            self._event(task, 'ASSIGNED')
            robot.pending_goal = (destination, 'NORMAL', robot.route[-1].arrive or self.now + 2.0)
            robot.yield_to, robot.yield_from, robot.yield_until = robot.yield_note, robot.route[0].node, self.now + 30.0
            return True, f'{task.id}: {robot.yield_note or "다른 로봇"}에게 길을 비켜 준 뒤 {destination}(으)로 이동'
        # [수정 2026-11-17] G2: 자동 배정 조건(_available) 대신 _movable
        if not self._movable(robot) or robot.route or robot.pending_goal or robot.reported_state != 'IDLE':
            return False, '로봇이 이동 가능한 대기 상태인지 확인하세요.'
        robot.heading = ''  # a failed route may still retain its last granted target
        robot.fail_count, robot.avoid_node = 0, ''
        start = self.graph.nearest_node(robot.x, robot.y)
        off = math.dist((robot.x, robot.y), self.graph.nodes[start])
        if off <= self.off_node_dist:
            if start == destination:
                return False, '이미 해당 노드에 있습니다.'
            if self._blocker(start, robot_id):
                return False, '출발 노드를 다른 로봇이 점유 중입니다.'
            self._claim_vertex(robot, start)
        else:
            # not on a node: the route starts with the drive back to the nearest free node
            if self.locks.get(start) in (None, robot_id):
                self._claim_vertex(robot, start)
            if not self._rejoin(robot):
                return False, f'로봇이 주행 노드에서 {off * 100:.0f}cm 벗어나 있고, {self.rejoin_max_dist:.0f}m 안에 비어 있는 노드가 없습니다.'
            start = robot.node
        self.seq += 1
        task = Task(f'M{self.seq:04d}', 'MOVE', created=self.now, start_node=destination,
                    phases=[('move', destination, 'NORMAL')])
        self.tasks[task.id] = task
        self._assign(task, robot)
        return True, f'{task.id}: {start} → {destination}' + (f' (노드에서 {off * 100:.0f}cm 벗어나 있어 {start}로 복귀 후 이동)'
                                                              if off > self.off_node_dist else '')

    # [수정 2026-11-18] W8-2: 이동 명령의 목적지 겹침 검사
    def _heading_near(self, destination: str, robot_id: str) -> str:
        """목적지나 그와 동시에 점유할 수 없는 노드로 가는 다른 로봇.

        Args:
            destination: 이동 명령의 목적지 노드.
            robot_id: 명령을 받을 로봇(제외).

        Returns:
            그런 로봇의 id. 없으면 ''. 비켜 서는 중인 자리(YIELD 경로의 끝)는
            잠시 머무는 곳이라 보지 않음.
        """
        region = {destination} | self.graph.conflict[destination]
        for o in self.robots.values():
            if o.id == robot_id or o.estop:
                continue
            goals = set()
            t = o.task
            if t and t.type == 'MOVE' and t.state == 'IN_PROGRESS':
                goals.add(self.graph.resolve(t.start_node))
            if o.pending_goal:
                goals.add(self.graph.resolve(o.pending_goal[0]))
            if o.route and o.mode != 'YIELD':
                goals.add(o.route[-1].node)
            if goals & region:
                return o.id
        return ''

    # [수정 2026-11-17] 신규: 관리자 화면의 홈 복귀 버튼(GO_HOME)
    def _send_home(self, target: str) -> tuple:
        """로봇 한 대 또는 연결된 모든 로봇을 홈으로 보냄.

        실측 지도에서는 출발 노드(homes)로 가는 이동 명령과 같고, 가상
        매장에서는 충전대로 복귀함. 임무 중이거나 비상 정지된 로봇은
        보내지 않음.

        Args:
            target: 로봇 이름. 'ALL' 이나 빈 값이면 연결된 모든 로봇.

        Returns:
            (성공 여부, 화면에 보여 줄 메시지). 전체 명령은 한 대라도
            출발했거나 모두 이미 홈이면 성공.

        Raises:
            KeyError: 없는 로봇 이름.
        """
        everyone = target in ('', 'ALL')
        robots = [r for r in self.robots.values() if r.online] \
            if everyone else [self.robots[target]]
        if not robots:
            return False, '연결된 로봇이 없습니다.'
        sent, notes = 0, []
        for r in robots:
            at_home = math.dist(
                (r.x, r.y), self.graph.nodes[r.home]) <= self.off_node_dist
            if at_home and not r.route and not r.task:
                sent += 1
                notes.append(f'{r.id}: 이미 홈({r.home})')
                continue
            if self.graph.map_id:
                ok, message = self._move_to_vertex(r.id, r.home)
            else:
                ok = self._movable(r) and not r.route
                message = f'{r.home}(으)로 복귀' if ok else \
                    '로봇이 이동 가능한 대기 상태인지 확인하세요.'
                if ok:
                    self._go_home(r, force_home=True)
            sent += bool(ok)
            notes.append(f'{r.id}: {message}')
            self.io.log('GO_HOME', robot_id=r.id, zone_id=r.home,
                        result='OK' if ok else 'FAIL', reason=message)
        return sent > 0, ' / '.join(notes)

    # ------------------------------------------------------------------ operator commands
    def command(self, cmd, target, arg=''):
        try:
            # [수정 2026-11-17] 홈 복귀 명령
            if cmd == 'GO_HOME':
                return self._send_home(target)
            if cmd == 'MOVE_TO_VERTEX':
                return self._move_to_vertex(target, arg)
            if cmd == 'SET_SCHEDULER':
                self.set_scheduler(target or arg)
                return True, f'scheduler={self.scheduler.name}'
            if cmd == 'SET_PLANNER':
                self.set_planner(target or arg)
                return True, f'planner={self.planner.name}'
            # [수정 2026-11-17] UR-18: 일시 중단. 비상 정지와 같은 통로
            # (생존 신호의 정지 목록)로 세우고 임무는 SUSPENDED(PAUSED) 로 둠.
            # RESUME 이 임무를 중단된 단계부터 이어서 수행
            if cmd == 'PAUSE':
                r = self.robots[target]
                if r.estop:
                    return False, f'{target} is already stopped'
                r.estop = r.paused = True
                if r.route:
                    self._stop_route(r)
                if r.arm_busy:
                    self.io.cancel_arm(r.id)
                r.pending_goal = None
                self.io.log('PAUSE', robot_id=r.id, zone_id=r.node, reason=arg)
                if r.task and r.task.state == 'IN_PROGRESS':
                    self._suspend(r.task, 'PAUSED')
                return True, f'{target} paused'
            if cmd == 'ESTOP':
                r = self.robots[target]
                r.estop, r.paused = True, False
                if r.route:
                    self._stop_route(r)
                if r.arm_busy:
                    self.io.cancel_arm(r.id)
                r.pending_goal = None
                self.io.log('ESTOP', robot_id=r.id, zone_id=r.node, reason=arg)
                if r.task and r.task.state == 'IN_PROGRESS':
                    self._suspend(r.task, 'E_STOP')
                return True, f'{target} stopped'
            if cmd == 'SET_STANDBY':
                self.use_standby = (target or arg).lower() in ('1', 'true', 'on')
                return True, f'standby={self.use_standby}'
            if cmd == 'RESUME':
                r = self.robots[target]
                r.estop, r.paused, r.fail_count = False, False, 0
                self.io.log('RESUME', robot_id=r.id, zone_id=r.node)
                if r.task and r.task.state == 'SUSPENDED':
                    return self.command('RETRY_TASK', r.task.id)
                if r.task is None:
                    self._go_home(r)
                return True, f'{target} resumed'
            if cmd == 'RETRY_TASK':
                t = self.tasks[target]
                if t.state != 'SUSPENDED':
                    return False, 'task is not suspended'
                if t.type == 'COOK':
                    t.state = 'IN_PROGRESS'
                    self._event(t, 'RESUMED')
                    return True, 'cook job resumed'
                r = self.robots[t.robot_id]
                if r.estop:
                    return False, 'robot is still in E-STOP; RESUME it first'
                t.state, t.reason = 'IN_PROGRESS', ''
                r.fail_count = 0
                # [수정 2026-11-18] W8-3: 재개하면 계획 실패 시간을 새로 셈
                r.plan_fail = None
                self._event(t, 'RESUMED')
                self._run_phase(r)
                return True, 'task resumed from the failed step'
            if cmd == 'REASSIGN':
                t = self.tasks[target]
                if t.state != 'SUSPENDED' or t.type not in AMR_TASKS:
                    return False, 'only a suspended AMR task can be reassigned'
                if t.carrying:
                    return False, 'food/dishes already loaded on the AMR: cannot hand over, remake required'
                old = self.robots.get(t.robot_id)
                if old:
                    old.task = None
                    if not old.estop:
                        self._go_home(old)
                t.robot_id, t.state, t.pi, t.reason = '', 'PENDING', 0, ''
                self._event(t, 'REASSIGNED')
                return True, 'task returned to the queue'
            if cmd == 'CANCEL_TASK':
                t = self.tasks[target]
                if t.state in ('DONE', 'CANCELED'):
                    return False, 'task already finished'
                r = self.robots.get(t.robot_id)
                t.state = 'CANCELED'
                self._event(t, 'CANCELED', arg)
                if r and r.task is t:
                    r.task = None
                    if not r.estop:
                        if r.route:
                            self._stop_route(r)
                        self._go_home(r)
                return True, 'task canceled'
        except KeyError as e:
            return False, f'unknown target {e}'
        return False, f'unknown command {cmd}'

    # ------------------------------------------------------------------ cooking cell
    def _recipe(self, menu):
        s = self.cook_scale
        fry = [('acq', {'ARM_A', 'FRYER'}), ('arm', 'A', 'LOAD_BASKET', 3.0), ('arm', 'A', 'DROP_IN_FRYER', 2.0),
               ('rel', {'ARM_A'}), ('timer', 600.0 / s, 'FRYING'), ('doneness',)]
        if menu == 'FRIED':
            return fry + [('acq', {'ARM_A', 'SLOT:FRY_PICKUP'}), ('arm', 'A', 'LIFT_DRAIN', 3.0), ('arm', 'A', 'PLATE', 3.0),
                          ('arm', 'A', 'PLACE_HANDOFF', 2.0), ('rel', {'ARM_A', 'FRYER'}), ('ready', 'FRY_PICKUP')]
        if menu == 'SEASONED':
            return fry + [('acq', {'ARM_A', 'ARM_B', 'WOK', 'SLOT:WOK_PICKUP'}), ('arm', 'A', 'LIFT_DRAIN', 3.0),
                          ('arm', 'A', 'TO_WOK', 3.0), ('rel', {'ARM_A', 'FRYER'}), ('arm', 'B', 'ADD_SAUCE', 2.0),
                          ('arm', 'B', 'STIR_FRY', 60.0 / s), ('arm', 'B', 'PLATE', 3.0), ('arm', 'B', 'PLACE_HANDOFF', 2.0),
                          ('rel', {'ARM_B', 'WOK'}), ('ready', 'WOK_PICKUP')]
        if menu == 'FRIED_RICE':
            return [('acq', {'ARM_A', 'ARM_B', 'WOK', 'SLOT:WOK_PICKUP'}), ('arm', 'A', 'ADD_INGREDIENTS', 3.0),
                    ('rel', {'ARM_A'}), ('arm', 'B', 'STIR_FRY', 300.0 / s), ('arm', 'B', 'PLATE', 3.0),
                    ('arm', 'B', 'PLACE_HANDOFF', 2.0), ('rel', {'ARM_B', 'WOK'}), ('ready', 'WOK_PICKUP')]
        raise ValueError(f'unknown menu {menu}')

    def _cook_tick(self):
        for j in list(self.cook_jobs):
            t = j.task
            if t.state != 'IN_PROGRESS':
                if t.state in ('CANCELED', 'DONE'):
                    self._cook_release(j, set(self.res_owner))
                    self.cook_jobs.remove(j)
                continue
            for _ in range(8):                              # advance through instant ops
                if j.busy or j.pc >= len(j.ops):
                    break
                op = j.ops[j.pc]
                if op[0] == 'acq':                          # all-or-nothing: never wait while holding an arm
                    arms = {x for x in op[1] if not x.startswith('SLOT:')}
                    slots = [x[5:] for x in op[1] if x.startswith('SLOT:')]
                    if any(self.res_owner[a] not in (None, t.id) for a in arms) or \
                       any(self.slots[s] >= self.slot_cap for s in slots):
                        break
                    for a in arms:
                        self.res_owner[a] = t.id
                    for s in slots:
                        self.slots[s] += 1
                    if j.pc == 0:
                        j.label = 'COOKING'
                        self._event(t, 'COOKING')
                    j.pc += 1
                elif op[0] == 'rel':
                    self._cook_release(j, op[1])
                    j.pc += 1
                elif op[0] == 'arm':
                    j.busy, j.label = True, op[2]
                    params = {'cook_task_id': t.id, 'menu': t.menu}
                    if op[2] == 'DROP_IN_FRYER':
                        params['fry_time'] = 600.0 / self.cook_scale
                    self.io.arm_job('cook_arm_a' if op[1] == 'A' else 'cook_arm_b', t.id, op[2], op[3], params)
                    self.io.log('COOK_STEP', task_id=t.id, order_id=t.order_id, robot_id='cook_arm_' + op[1].lower(),
                                result=op[2])
                elif op[0] == 'timer':
                    if j.until == 0.0:
                        j.until, j.label = self.now + op[1], op[2]
                        self.io.log('COOK_STEP', task_id=t.id, order_id=t.order_id, result=op[2], reason=f'{op[1]:.1f}s')
                        break
                    if self.now < j.until:
                        break
                    j.until = 0.0
                    j.pc += 1
                elif op[0] == 'doneness':
                    if not self.use_doneness:
                        j.pc += 1
                        continue
                    if j.wait_doneness_since is None:
                        j.wait_doneness_since, j.label = self.now, 'DONENESS_CHECK'
                    d = self.doneness.get(t.id)
                    fresh = d and d[1] >= j.wait_doneness_since
                    if not fresh and self.now - j.wait_doneness_since < 5.0:
                        break
                    decision = d[0] if fresh else 'DONE'           # AI server silent: degrade to timer only
                    self.io.log('DONENESS', task_id=t.id, order_id=t.order_id, result=decision,
                                reason='ai' if fresh else 'timeout_fallback')
                    j.wait_doneness_since = None
                    if decision == 'UNDERCOOKED' and j.retries < 2:
                        j.retries += 1
                        j.ops.insert(j.pc, ('timer', 120.0 / self.cook_scale, f'REFRY_{j.retries}'))
                        continue
                    j.pc += 1
                elif op[0] == 'ready':
                    t.state, t.finished_at, j.label = 'DONE', self.now, 'READY'
                    self.io.log('COOK_READY', task_id=t.id, order_id=t.order_id, zone_id=op[1],
                                reason=f'dur={self.now - t.created:.1f}')
                    self._event(t, 'READY', op[1])
                    self.cook_jobs.remove(j)
                    break

    def _cook_release(self, j, names):
        for a in names:
            if not a.startswith('SLOT:') and self.res_owner.get(a) == j.task.id:
                self.res_owner[a] = None

    # ------------------------------------------------------------------ state for UI
    def robot_state(self, r):
        if r.estop:
            # [수정 2026-11-17] UR-18: 일시 중단은 따로 표시
            return 'PAUSED' if r.paused else 'E_STOP'
        t = r.task
        if t and t.state == 'SUSPENDED':
            return 'SUSPENDED'
        if r.arm_busy:
            return {'LOAD': 'LOADING', 'UNLOAD': 'UNLOADING', 'COLLECT_DISHES': 'COLLECTING',
                    'RETURN_DISHES': 'RETURNING_DISHES'}.get(r.arm_busy, r.arm_busy)
        if t:
            if t.type == 'MOVE':
                return 'MOVING'
            if t.type == 'GUIDE':
                return 'GUIDING' if t.pi >= 2 else 'TO_START'
            if t.type == 'SERVE':
                return 'SERVING' if t.carrying else 'TO_PICKUP'
            return 'TO_DISH_RETURN' if t.carrying else 'TO_TABLE'
        if r.returning or r.route:
            return 'RETURNING'
        if r.node in self.graph.standby_nodes:
            return 'STANDBY'
        return 'CHARGING' if r.charging else 'IDLE'

    def active_grants(self):
        """(robot, task id, plan version, granted index) of every route that holds a permission: the node repeats
        them so that a lost TrafficGrant message cannot leave a robot waiting for ever."""
        return [(r.id, r.task.id if r.task else 'RETURN', r.plan_version, r.granted)
                for r in self.robots.values() if r.route and r.granted > 0 and not r.estop]

    def estopped(self):
        return [r.id for r in self.robots.values() if r.estop]

    def _off_node(self, r):
        return bool(r.online and not r.route and not r.heading
                    and math.dist((r.x, r.y), self.graph.nodes[r.node]) > self.off_node_dist)

    def _arm_job_of(self, arm):
        """Arm job a cooking arm ('A' / 'B') is running right now, '' when it stands still."""
        for j in self.cook_jobs:
            if j.busy and j.pc < len(j.ops) and j.ops[j.pc][0] == 'arm' and j.ops[j.pc][1] == arm:
                return j.ops[j.pc][2]
        return ''

    def snapshot(self):
        return {
            'now': self.now,
            'map_id': self.graph.map_id,
            'algorithms': {'scheduler': self.scheduler.name, 'planner': self.planner.name,
                           'schedulers': {k: v.description for k, v in SCHEDULERS.items()},
                           'planners': {k: v.description for k, v in PLANNERS.items()}, 'standby': self.use_standby},
            # [수정 2026-11-17] UR-17~21: paused, fault_since, at_home,
            # available, unavailable_reason, arm 추가. 일시 중단 중에는 로봇이
            # 보고하는 EMERGENCY_STOP(정지 목록에 든 결과)을 오류로 보이지 않음
            'min_battery': self.min_battery,
            'robots': [{'id': r.id, 'state': self.robot_state(r), 'node': r.node, 'heading': r.heading,
                        'device': device_state.mobile_state(self.robot_state(r), r.online,
                                                            error='' if r.paused else r.error),
                        'error': '' if r.paused else r.error,
                        'paused': r.paused, 'fault_since': dict(r.fault_since),
                        'at_home': r.node == r.home and not r.heading and not r.route,
                        'available': self._available(r),
                        'unavailable_reason': self._unavailable_reason(r),
                        'arm': self._serving_arm(r), 'off_node': self._off_node(r), 'yield_to': r.yield_to or r.yield_note,
                        'x': r.x, 'y': r.y, 'yaw': r.yaw, 'battery': round(r.battery, 1), 'charging': r.charging,
                        'task': r.task.id if r.task else '', 'task_type': r.task.type if r.task else '',
                        'carrying': bool(r.task and r.task.carrying), 'plan_version': r.plan_version,
                        'blocked_by': r.blocked_by if r.wait_since is not None else '', 'online': r.online,
                        'route': [s.node for s in r.route[max(r.idx, 0):]] if r.route else [],
                        'dist': round(r.dist, 2)} for r in self.robots.values()],
            'tasks': [{'id': t.id, 'type': t.type, 'state': t.state, 'robot': t.robot_id, 'table': t.table_id,
                       'menu': t.menu, 'visit': t.visit_id, 'order': t.order_id, 'item': t.item_id,
                       'reason': t.reason, 'age': round(self.now - t.created, 1), 'carrying': t.carrying}
                      for t in list(self.tasks.values())[-40:]],
            'locks': dict(self.locks),
            'cooking': {'resources': dict(self.res_owner), 'slots': dict(self.slots),
                        'arms': {f'cook_arm_{a.lower()}': self._cook_arm_device(f'cook_arm_{a.lower()}', a)
                                 for a in 'AB'},
                        # [수정 2026-11-18] W2: v4 조리 작업 상태 state 추가
                        # (step 은 화면이 쓰는 공정 단계 이름이라 그대로 둠)
                        'jobs': [{'task': j.task.id, 'menu': j.task.menu,
                                  'step': j.label, 'state': _cook_state(j),
                                  'order': j.task.order_id,
                                  'retries': j.retries}
                                 for j in self.cook_jobs]},
            'metrics': {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.m.items()},
        }
