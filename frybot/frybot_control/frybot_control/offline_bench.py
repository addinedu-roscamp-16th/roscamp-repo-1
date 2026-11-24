"""Offline algorithm comparison: runs the real Task Manager core + restaurant logic against simple kinematic robots
(no ROS, faster than real time) and prints one row per (scheduler, planner) pair for the same customer script.

    ros2 run frybot_control fleet_bench            # all combinations
    ros2 run frybot_control fleet_bench --scenario rush --schedulers min_cost --planners sipp independent_astar

[수정 2026-11-18] W3: 모의 로봇을 mock_fleet.MockFleet 으로 바꾸고 비교 기능
추가
    --time-model ideal|measured  실행 시간 모델
                                 ideal: 지연 0, 0.08 m/s
                                 measured: 2.27초 + 거리 / 0.135 m/s
    --overhead, --exec-speed     시간 모델 값 직접 지정
    --jitter 0.2                 구간 시간에 곱하는 흔들림(0.8~1.2배)
    --plan-speed 0.135           관제의 일반 속도(m/s, FleetCore speed).
                                 기본 0.08
                                 [수정 2026-11-18] W10: 실기기 런치의 speed:=
                                 와 같게 바꿈(예전에는 배율로 넘겨 안내
                                 속도까지 바뀜). 계획 속도 = 값 x 배율
    --plan-guide-speed 0.05      관제의 손님 안내 속도(m/s). 기본 0.05
    --plan-speed-factor 1.0      계획 속도 배율. 기본 관제 기본값 0.9
    --baseline "fifo_nearest independent_astar"
                                 같은 씨앗끼리 짝지어 기준선과 비교
    --check                      통과 기준 판정, 못 넘으면 종료 코드 1
                                 (전부 완료, 계획에 없는 정지 30초 0
                                 [W7: 의도된 대기는 빼고 셈],
                                 의도된 대기 20초 0
                                 [수정 2026-11-18] W11 추가,
                                 같은 목적지 계획 실패가 20초 넘게 이어진
                                 경우 0, 최소 간격 0.155 m)
                                 [수정 2026-11-18] W4: PLAN_FAIL 연속
                                 3회 기준을 20초 기준으로 바꿈
    --only-seed N                씨앗 하나만 실행(문제 실행을 다시 볼 때)
    --map-id test_map_v001 --scenario moves --robots 2
                                 실측 지도에서 씨앗으로 정한 이동 명령
    --csv 원본(씨앗당 한 줄), --csv-mean 조합별 평균(예전 --csv 형식)
    --jobs N 병렬 실행
    --plan-overhead 2.27         [수정 2026-11-18] W6: 관제의 계획 구간 지연(초)
"""

import argparse
import csv
import math
import multiprocessing
import os
import random
import statistics as st

from .layout import robot_ids
from .mock_fleet import MEASURED_OVERHEAD
from .mock_fleet import MEASURED_SPEED
from .mock_fleet import MockFleet
from .mock_fleet import TimeModel
from .planners import PLANNERS
from .restaurant import Restaurant
from .restaurant import RestaurantIO
from .schedulers import SCHEDULERS

# (arrival time s, party size, [(menu, qty)], seconds from seated to order, seconds from last dish to leaving)
SCENARIOS = {
    'normal': [(0, 2, [('FRIED', 1)], 8, 25), (20, 4, [('FRIED_RICE', 2), ('SEASONED', 1)], 10, 30),
               (45, 2, [('FRIED_RICE', 1)], 8, 25), (80, 3, [('FRIED', 1), ('FRIED_RICE', 1)], 10, 30),
               (120, 2, [('SEASONED', 1)], 8, 25)],
    # entrance guiding and pick-ups at the same moment + long hand-overs at tables on the aisles
    'bottleneck': [(0, 2, [('FRIED_RICE', 2)], 4, 30), (2, 2, [('FRIED_RICE', 2)], 4, 30), (4, 4, [('FRIED_RICE', 2), ('FRIED', 1)], 4, 30),
                   (34, 2, [('FRIED_RICE', 1)], 4, 20), (36, 4, [('FRIED_RICE', 2)], 4, 20), (38, 2, [('FRIED_RICE', 2)], 4, 20),
                   (100, 2, [('FRIED_RICE', 1)], 4, 20), (102, 2, [('SEASONED', 1)], 4, 20)],
    'rush': [(0, 2, [('FRIED_RICE', 1)], 5, 20), (3, 4, [('FRIED_RICE', 2)], 5, 25), (6, 2, [('FRIED', 1)], 5, 20),
             (9, 4, [('FRIED_RICE', 1), ('SEASONED', 1)], 5, 25), (12, 2, [('FRIED_RICE', 2)], 5, 20),
             (15, 2, [('FRIED_RICE', 1)], 5, 20), (70, 2, [('FRIED_RICE', 1)], 5, 20), (75, 4, [('FRIED', 1), ('FRIED_RICE', 2)], 5, 20),
             (140, 2, [('FRIED_RICE', 1)], 5, 20), (145, 2, [('SEASONED', 1)], 5, 20)],
}
# [수정 2026-11-18] W3: 실측 지도 작업 부하(가상 매장 손님 대본이 아님)
MOVES = 'moves'
MOVES_PER_ROBOT = 8
# [수정 2026-11-18] W8-2: 거절된 이동 명령을 다시 시도하는 횟수(1초 간격)
MOVE_RETRIES = 60
# [수정 2026-11-18] W3: --check 통과 기준
# (작업 지시서 0장 중 모의로 볼 수 있는 것)
CHECK_MIN_SEP = 0.155
# [수정 2026-11-18] W4: PLAN_FAIL 연속 3회 기준(CHECK_FAIL_RUN)을 지우고
# 같은 목적지 계획 실패 20초 넘는 묶음 0건 기준으로 바꿈(mock_fleet 참고)


# [수정 2026-11-18] W3: SimRobot 과 이동 코드는 mock_fleet 으로 옮겨 삭제함
class OfflineWorld(MockFleet, RestaurantIO):
    """가상 매장 손님 대본을 관제 코어 + 모의 로봇으로 실행함."""

    # [수정 2026-11-18] W3: 시간 모델(model)·흔들림 씨앗(seed)·계획 속도
    # 인자 추가
    def __init__(
        self,
        scheduler,
        planner,
        scenario,
        dt=0.1,
        speed=0.08,
        guide_speed=0.05,
        cook_scale=20.0,
        verbose=False,
        standby=True,
        robots=3,
        model=None,
        seed=0,
        plan_speed=None,
        plan_overhead=None,
        plan_guide_speed=None,
        plan_speed_factor=None,
    ):
        model = model or TimeModel('ideal', speed, 0.0, guide_speed=guide_speed)
        # [수정 2026-11-18] W10: 계획 속도는 배율 대신 FleetCore 의 speed·
        # guide_speed 로 넘김(_plan_args)
        core_args = _plan_args(speed, guide_speed, plan_speed, plan_overhead,
                               plan_guide_speed, plan_speed_factor)
        super().__init__(
            robot_ids(robots),
            model,
            dt=dt,
            seed=seed,
            scheduler=scheduler,
            planner=planner,
            cook_time_scale=cook_scale,
            use_doneness=False,
            use_standby=standby,
            **core_args,
        )
        self.verbose = verbose
        self.rest = Restaurant(self)
        self.todo = [(a[0], 'arrive', a) for a in scenario]
        self.plan_of = {}  # visit -> scenario row
        self.stats = dict(
            seat=[], deliver=[], ready_to_deliver=[], turnaround=[], rejected=0
        )

    def log(self, event, **f):
        """관제·매장 로그. 서비스 시간을 모음."""
        super().log(event, **f)
        if self.verbose:
            print(
                f'{self.t:7.1f} {event:15s}',
                {k: v for k, v in f.items() if v != ''},
            )
        r = f.get('reason', '')
        if event == 'SEATED':
            self.stats['seat'].append(float(r.split('=')[1]))
        elif event == 'DELIVERED':
            a, b = r.split()
            self.stats['deliver'].append(float(a.split('=')[1]))
            self.stats['ready_to_deliver'].append(float(b.split('=')[1]))
        elif event == 'TABLE_AVAILABLE' and r:
            self.stats['turnaround'].append(float(r.split('=')[1]))
        elif event == 'CHECKIN_REJECT':
            self.stats['rejected'] += 1

    # ---- RestaurantIO
    def submit_task(self, cb, **kw):
        """매장 -> 관제 임무 요청."""
        kw['type'] = kw.pop('task_type')
        cb(self.core.submit_task(**kw))

    def fleet_command(self, cmd, target, arg=''):
        """매장 -> 관제 명령."""
        return self.core.command(cmd, target, arg)

    def persist(self, table, row):
        """DB 저장(모의에서는 하지 않음)."""

    # ---- simulation
    def report(self, bot):
        """예전 모의 로봇과 같은 형식으로 상태를 보고함(방향 0, 상태 없음)."""
        self.core.on_robot_status(bot.id, bot.x, bot.y, 0.0, 100.0, False, '')

    def step(self):
        """한 단계(dt 초): 손님 대본, 로봇, 매장, 관제 순서."""
        self.t += self.dt
        t = self.t
        for item in [x for x in self.todo if x[0] <= t]:
            self.todo.remove(item)
            _, kind, a = item
            if kind == 'arrive':
                ok, vid, _, _ = self.rest.check_in(a[1])
                if ok:
                    self.plan_of[vid] = a
            elif kind == 'order':
                v = self.rest.visits[a]
                self.rest.place_order(v['table'], self.plan_of[a][2])
            elif kind == 'leave':
                self.rest.end_use(self.rest.visits[a]['table'], 'TABLET')
        self.move_robots()
        self.rest.tick(t)
        self.core.tick(t)
        for ev in self.task_events:
            self.rest.on_task_event(ev)
            if ev['task_type'] == 'GUIDE' and ev['state'] == 'ARRIVED':
                self.todo.append(
                    (
                        t + self.plan_of[ev['visit_id']][3],
                        'order',
                        ev['visit_id'],
                    )
                )
            if ev['task_type'] == 'SERVE' and ev['state'] == 'DELIVERED':
                o = self.rest.orders[ev['order_id']]
                if o['state'] == 'COMPLETED':
                    self.todo.append(
                        (t + self.plan_of[o['visit']][4], 'leave', o['visit'])
                    )
        self.task_events.clear()

    def finished(self):
        """손님 대본이 끝나고 모든 테이블·로봇이 비었는지."""
        return (
            not self.todo
            and all(
                t['state'] == 'AVAILABLE' for t in self.rest.tables.values()
            )
            and all(
                r.task is None and not r.route and not r.pending_goal
                for r in self.core.robots.values()
            )
        )


# [수정 2026-11-18] W10: 계획 인자를 실기기 런치(task_manager 의 speed,
# guide_speed)와 같은 방식으로 FleetCore 에 넘김
def _plan_args(
    speed: float,
    guide_speed: float,
    plan_speed: float | None = None,
    plan_overhead: float | None = None,
    plan_guide_speed: float | None = None,
    plan_speed_factor: float | None = None,
) -> dict:
    """계획 인자를 FleetCore 인자로 바꿈.

    Args:
        speed: 관제 기본 일반 속도(m/s).
        guide_speed: 관제 기본 안내 속도(m/s).
        plan_speed: 일반 속도(m/s). None 이면 speed.
        plan_overhead: 계획의 구간 지연(초). None 이면 관제 기본값(0).
        plan_guide_speed: 안내 속도(m/s). None 이면 guide_speed.
        plan_speed_factor: 계획 속도 배율. None 이면 관제 기본값(0.9).

    Returns:
        FleetCore 에 넘길 인자 dict.
    """
    core_args = dict(speed=plan_speed or speed,
                     guide_speed=plan_guide_speed or guide_speed)
    if plan_overhead:
        core_args['plan_overhead'] = plan_overhead
    if plan_speed_factor is not None:
        core_args['plan_speed_factor'] = plan_speed_factor
    return core_args


def _mock_metrics(w: MockFleet) -> dict:
    """MockFleet 이 센 공통 지표."""
    return dict(
        stall30=w.stall30,
        # [수정 2026-11-18] W7: 서 있는 이유별 지표
        unplanned30=w.unplanned30,
        intended30=w.intended30,
        intended_wait_max=round(w.intended_wait_max, 1),
        # [수정 2026-11-18] W10: 구간 출발 지연 합계(초, 참고)
        start_delay_sum=round(w.start_delay_sum, 1),
        # [수정 2026-11-18] W11: 의도된 대기 20초(판정)와 종류별 수, 계획에
        # 없는 정지 20초(참고)
        intended20=w.intended20,
        intended20_plan=w.intended20_kind['plan'],
        intended20_yield=w.intended20_kind['yield'],
        intended20_arm=w.intended20_kind['arm'],
        unplanned20=w.unplanned20,
        plan_fail_run=w.plan_fail_run,
        # [수정 2026-11-18] W4: 20초 넘는 계획 실패 묶음 수와 위치
        # (로봇@목적지:첫 시각-마지막 시각, 세미콜론으로 구분)
        plan_fail_long=len(w.fail_long_all()),
        plan_fail_long_at=';'.join(
            f'{rid}@{dest}:{t0:.0f}-{t1:.0f}'
            for rid, dest, t0, t1 in w.fail_long_all()
        ),
        close_time=round(w.close_time, 1),
        suspended=w.suspended,  # [수정 2026-11-18] W8-3
        # [수정 2026-11-18] W6: 계획 ETA 대비 실제 소요 비율의 중앙값
        eta_ratio=(round(st.median(w.eta_ratios), 3) if w.eta_ratios
                   else float('nan')),
    )


# [수정 2026-11-18] W3: run() 의 인자·반환 열은 그대로 두고
# (scripts/bench_all.py), 시간 모델·계획 속도 인자와 공통 지표 열만 덧붙임.
# 전달 시간 목록은 _run_full 이 따로 돌려줌
def _run_full(
    scheduler,
    planner,
    scenario='normal',
    max_t=1500.0,
    verbose=False,
    standby=True,
    seed=0,
    robots=3,
    model=None,
    plan_speed=None,
    plan_overhead=None,
    plan_guide_speed=None,
    plan_speed_factor=None,
):
    random.seed(seed)
    script = SCENARIOS[scenario]
    if seed:  # same guests, arrival times shifted a little per seed
        script = sorted(
            (max(0.0, a[0] + random.uniform(-4, 4)),) + a[1:] for a in script
        )
    w = OfflineWorld(
        scheduler,
        planner,
        script,
        verbose=verbose,
        standby=standby,
        robots=robots,
        model=model,
        seed=seed,
        plan_speed=plan_speed,
        plan_overhead=plan_overhead,
        plan_guide_speed=plan_guide_speed,
        plan_speed_factor=plan_speed_factor,
    )
    # [수정 2026-11-18] W8-3: 관제가 임무를 보류하면 시간 한도까지 기다리지
    # 않고 끝냄(보류 수는 suspended 로 셈)
    while w.t < max_t and not (w.t > 5 and w.finished()) and not w.suspended:
        w.step()
    m, s = w.core.m, w.stats

    def avg(a):
        return round(st.mean(a), 1) if a else float('nan')

    row = dict(
        scheduler=scheduler,
        planner=planner,
        finished=w.finished(),
        makespan=round(w.t, 1),
        seat_avg=avg(s['seat']),
        deliver_avg=avg(s['deliver']),
        deliver_max=round(max(s['deliver'], default=0), 1),
        ready_to_deliver=avg(s['ready_to_deliver']),
        turnaround=avg(s['turnaround']),
        rejected=s['rejected'],
        blocked_wait=round(m['blocked_wait'], 1),
        stalls=m['stalls'],
        replans=m['replans'],
        retreats=m['retreats'],
        flips=m['flips'],
        plan_fail=m['plan_fail'],
        plan_ms=round(m['plan_ms'] / max(1, m['plan_calls']), 2),
        dist=round(sum(r.dist for r in w.core.robots.values()), 1),
        min_sep=round(w.min_sep, 3),
        tasks=m['tasks_done'],
        reassign=m['reassign'],
        joint=m['joint_plans'],
        **_mock_metrics(w),
    )
    return row, list(s['deliver'])


def run(
    scheduler,
    planner,
    scenario='normal',
    max_t=1500.0,
    verbose=False,
    standby=True,
    seed=0,
    robots=3,
    model=None,
    plan_speed=None,
    plan_overhead=None,
    plan_guide_speed=None,
    plan_speed_factor=None,
):
    """한 조합·한 씨앗을 실행해 지표 한 줄을 돌려줌."""
    # [수정 2026-11-18] W10: 안내 속도·계획 속도 배율 전달
    return _run_full(
        scheduler,
        planner,
        scenario,
        max_t,
        verbose,
        standby,
        seed,
        robots,
        model,
        plan_speed,
        plan_overhead,
        plan_guide_speed,
        plan_speed_factor,
    )[0]


# [수정 2026-11-18] W3: 실측 지도 이동 명령 작업 부하
def _moves_plan(graph, rids: list[str], seed: int, per_robot: int) -> dict:
    """로봇마다 씨앗으로 정한 목적지 목록(연속으로 같은 노드는 없음)."""
    rng = random.Random(seed * 7919 + 1)
    major = sorted(n for n in graph.nodes if '_' not in n)
    plan = {}
    for rid in rids:
        last, dests = graph.home_of(rid), []
        while len(dests) < per_robot:
            dest = rng.choice(major)
            if dest != last:
                dests.append(dest)
                last = dest
        plan[rid] = dests
    return plan


def _free_time(graph, model: TimeModel, src: str, dst: str) -> float:
    """막힘 없이 src -> dst 를 갈 때의 시간(빈 지도 최단 경로, 흔들림 없음)."""
    dist = graph.sp_from(dst)
    node, total = src, 0.0
    while node != dst:
        nxt, d = min(graph.adj[node], key=lambda e: e[1] + dist.get(e[0], 1e18))
        total += model.segment_time(d)
        node = nxt
    return total


def run_moves(
    scheduler,
    planner,
    seed=0,
    robots=2,
    model=None,
    plan_speed=None,
    max_t=1500.0,
    per_robot=MOVES_PER_ROBOT,
    plan_overhead=None,
    plan_speed_factor=None,
):
    """실측 지도에서 이동 명령 대본을 실행함.

    Args:
        scheduler: 스케줄러 이름(이동 명령은 로봇을 지정하므로 영향 없음).
        planner: 플래너 이름.
        seed: 명령 대본과 흔들림의 씨앗.
        robots: 로봇 대수.
        model: 실행 시간 모델.
        plan_speed: 계획 속도(m/s). None 이면 관제 기본값.
        max_t: 최대 모의 시간(초).
        per_robot: 로봇마다 보낼 이동 명령 수.
        plan_overhead: 계획의 구간 지연(초). None 이면 관제 기본값(0).
        plan_speed_factor: 계획 속도 배율. None 이면 관제 기본값(0.9).

    Returns:
        (지표 dict, 명령별 '소요 / 막힘 없는 소요' 목록).
    """
    speed = 0.08
    model = model or TimeModel('ideal', speed, 0.0)
    core_args = dict(scheduler=scheduler, planner=planner, pv_base=0)
    # [수정 2026-11-18] W10: 계획 속도는 FleetCore 의 speed 로 넘김
    core_args.update(_plan_args(speed, 0.05, plan_speed, plan_overhead,
                                None, plan_speed_factor))
    # [수정 2026-11-18] W8-1: 관제 코어의 난수는 MockFleet 이 rng_seed 로
    # 넘기므로 전역 random.seed 를 지움
    rids = robot_ids(robots)
    w = MockFleet(rids, model, dt=0.1, seed=seed, **core_args)
    graph = w.core.graph
    plan = _moves_plan(graph, rids, seed, per_robot)
    for _ in range(3):
        w.step()
    rng = random.Random(seed * 7919 + 2)
    next_at = {rid: w.t + rng.uniform(0.0, 2.0) for rid in rids}
    tries = {rid: 0 for rid in rids}
    sent, rejected = [], 0
    # [수정 2026-11-18] W8-2: 관제가 거절한 시도 수(이미 그 노드인 경우 제외)
    refused = 0
    while w.t < max_t:
        w.step()
        for rid in rids:
            r = w.core.robots[rid]
            if (
                not plan[rid]
                or w.t < next_at[rid]
                or r.task
                or r.route
                or r.pending_goal
            ):
                continue
            dest = plan[rid][0]
            src = graph.nearest_node(r.x, r.y)
            ok, _ = w.core.command('MOVE_TO_VERTEX', rid, dest)
            if ok and r.task:
                sent.append(
                    dict(
                        rid=rid,
                        task=r.task.id,
                        t0=w.t,
                        free=_free_time(graph, model, src, dest),
                    )
                )
                plan[rid].pop(0)
                tries[rid] = 0
            elif (
                # [수정 2026-11-18] W8-2: 거절된 명령은 1분(60번) 동안 다시
                # 시도한 뒤 건너뜀(전에는 10번). 같은 목적지로 가는 로봇의
                # 도착을 기다리게 함
                src == dest or tries[rid] >= MOVE_RETRIES
            ):  # 이미 그 노드이거나 계속 거절: 이 명령은 건너뜀
                plan[rid].pop(0)
                tries[rid] = 0
                rejected += src != dest
            else:
                tries[rid] += 1
                refused += 1
                next_at[rid] = w.t + 1.0
        if not any(plan.values()) and w.idle():
            break
        if w.suspended:                    # [수정 2026-11-18] W8-3: 보류로 끝남
            break
    done = {e['task_id']: e['t'] for e in w.events if e['event'] == 'TASK_DONE'}
    ratios, waits = [], []
    for c in sent:
        if c['task'] in done:
            dur = done[c['task']] - c['t0']
            ratios.append(dur / c['free'] if c['free'] > 0 else 1.0)
            waits.append(max(0.0, dur - c['free']))
    m = w.core.m
    finished = not any(plan.values()) and w.idle() and len(ratios) == len(sent)
    row = dict(
        scheduler=scheduler,
        planner=planner,
        finished=finished,
        makespan=round(w.t, 1),
        commands=len(sent),
        rejected=rejected,
        refused=refused,
        ratio_med=round(st.median(ratios), 2) if ratios else float('nan'),
        ratio_max=round(max(ratios), 2) if ratios else float('nan'),
        wait_total=round(sum(waits), 1),
        blocked_wait=round(m['blocked_wait'], 1),
        stalls=m['stalls'],
        replans=m['replans'],
        retreats=m['retreats'],
        yields=m['yields'],
        flips=m['flips'],
        plan_fail=m['plan_fail'],
        plan_ms=round(m['plan_ms'] / max(1, m['plan_calls']), 2),
        dist=round(sum(r.dist for r in w.core.robots.values()), 1),
        min_sep=round(w.min_sep, 3),
        tasks=m['tasks_done'],
        **_mock_metrics(w),
    )
    return row, ratios


COLS = [
    'scheduler',
    'planner',
    'finished',
    'makespan',
    'seat_avg',
    'deliver_avg',
    'deliver_max',
    'ready_to_deliver',
    'turnaround',
    'blocked_wait',
    'stalls',
    'replans',
    'retreats',
    'flips',
    'plan_fail',
    'plan_ms',
    'dist',
    'min_sep',
    'reassign',
    'joint',
    'tasks',
]
# [수정 2026-11-18] W3: 이동 명령 작업 부하의 열, 공통 지표 열
MOVE_COLS = [
    'scheduler',
    'planner',
    'finished',
    'makespan',
    'commands',
    'rejected',
    'refused',  # [수정 2026-11-18] W8-2
    'ratio_med',
    'ratio_max',
    'wait_total',
    'blocked_wait',
    'stalls',
    'replans',
    'retreats',
    'yields',
    'flips',
    'plan_fail',
    'plan_ms',
    'dist',
    'min_sep',
    'tasks',
]
# [수정 2026-11-18] W4: plan_fail_long(판정), plan_fail_long_at(위치) 추가
EXTRA_COLS = [
    'eta_ratio',  # [수정 2026-11-18] W6
    'stall30',
    'unplanned30',  # [수정 2026-11-18] W7
    'intended30',
    'intended_wait_max',
    'start_delay_sum',  # [수정 2026-11-18] W10
    'intended20',  # [수정 2026-11-18] W11
    'intended20_plan',
    'intended20_yield',
    'intended20_arm',
    'unplanned20',
    'plan_fail_run',
    'plan_fail_long',
    'close_time',
    'suspended',  # [수정 2026-11-18] W8-3
    'plan_fail_long_at',
]


def _job(args):
    """병렬 실행 한 건: (조합, 씨앗) -> (지표, 목록)."""
    # [수정 2026-11-18] W6: 계획 구간 지연(plan_overhead) 추가
    # [수정 2026-11-18] W10: 안내 속도·계획 속도 배율 추가
    (scenario, s, p, seed, robots, model, plan_speed, standby, max_t,
     plan_overhead, plan_guide_speed, plan_speed_factor) = args
    if scenario == MOVES:
        return run_moves(
            s,
            p,
            seed=seed,
            robots=robots,
            model=model,
            plan_speed=plan_speed,
            max_t=max_t,
            plan_overhead=plan_overhead,
            plan_speed_factor=plan_speed_factor,
        )
    return _run_full(
        s,
        p,
        scenario,
        max_t=max_t,
        standby=standby,
        seed=seed,
        robots=robots,
        model=model,
        plan_speed=plan_speed,
        plan_overhead=plan_overhead,
        plan_guide_speed=plan_guide_speed,
        plan_speed_factor=plan_speed_factor,
    )


def _passes(rows: list[dict]) -> tuple[bool, str]:
    """--check 통과 기준. 못 넘은 이유를 함께 돌려줌."""
    why = []
    if not all(r['finished'] for r in rows):
        why.append(f"미완료 {sum(not r['finished'] for r in rows)}")
    # [수정 2026-11-18] W8-3: 보류로 끝난 실행은 따로 알림
    if sum(r['suspended'] for r in rows):
        why.append(f"보류 {sum(r['suspended'] for r in rows)}")
    # [수정 2026-11-18] W7: 30초 정지는 계획에 없는 정지만(unplanned30)
    if sum(r['unplanned30'] for r in rows):
        why.append(f"계획 없는 정지 {sum(r['unplanned30'] for r in rows)}")
    # [수정 2026-11-18] W11: 의도된 대기가 20초 넘게 이어진 경우
    if sum(r['intended20'] for r in rows):
        why.append(f"의도된 대기 20초 {sum(r['intended20'] for r in rows)}")
    # [수정 2026-11-18] W4: 같은 목적지 계획 실패가 20초 넘게 이어진 경우
    if sum(r['plan_fail_long'] for r in rows):
        why.append(f"계획 실패 20초 {sum(r['plan_fail_long'] for r in rows)}")
    if min(r['min_sep'] for r in rows) < CHECK_MIN_SEP - 1e-6:
        why.append(f"최소 간격 {min(r['min_sep'] for r in rows):.3f}")
    return not why, ', '.join(why)


def _p95(values: list[float]) -> float:
    """상위 5% 값(최근접 순위)."""
    if not values:
        return float('nan')
    values = sorted(values)
    return round(
        values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)], 1
    )


def _spread(values: list[float]) -> str:
    """'중앙값 [최소~최대]'."""
    values = [v for v in values if v == v]
    if not values:
        return 'nan'
    return f'{st.median(values):.1f} [{min(values):.1f}~{max(values):.1f}]'


def _model_of(a) -> TimeModel:
    """명령행 인자에서 실행 시간 모델을 만듦."""
    if a.time_model == 'measured':
        model = TimeModel(
            'measured', MEASURED_SPEED, MEASURED_OVERHEAD, guide_speed=0.05
        )
    else:
        model = TimeModel('ideal', 0.08, 0.0, guide_speed=0.05)
    if a.exec_speed is not None:
        model.speed = a.exec_speed
    if a.overhead is not None:
        model.overhead = a.overhead
    model.jitter = a.jitter
    if a.scenario == MOVES:
        model.guide_speed = None  # 이동 명령에는 손님 안내가 없음
    return model


def main():
    """명령행 진입점."""
    # [수정 2026-11-18] W8-1: 해시 씨앗 재실행(fix_hash_seed) 삭제. 관제
    # 코어가 정렬된 순서로 판단함
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        '--scenario', default='normal', choices=sorted(SCENARIOS) + [MOVES]
    )
    ap.add_argument('--schedulers', nargs='*', default=sorted(SCHEDULERS))
    ap.add_argument('--planners', nargs='*', default=sorted(PLANNERS))
    ap.add_argument('--csv', default='', help='raw rows, one per (pair, seed)')
    ap.add_argument(
        '--csv-mean',
        default='',
        help='one mean row per pair (the old --csv format)',
    )
    ap.add_argument(
        '--seeds',
        type=int,
        default=1,
        help='runs per pair (arrival times jittered); values are means',
    )
    ap.add_argument(
        '--robots', type=int, default=3, help='number of AMRs (pinky1..N)'
    )
    ap.add_argument('--verbose', action='store_true')
    # [수정 2026-11-18] W5: 씨앗 하나만 다시 실행
    ap.add_argument(
        '--only-seed', type=int, help='run this one seed only'
    )
    ap.add_argument(
        '--no-standby',
        action='store_true',
        help='idle robots always return to their charger',
    )
    ap.add_argument(
        '--time-model', default='ideal', choices=('ideal', 'measured')
    )
    ap.add_argument(
        '--overhead',
        type=float,
        help='per-segment delay of the mock robots (s)',
    )
    ap.add_argument(
        '--exec-speed',
        type=float,
        help='driving speed of the mock robots (m/s)',
    )
    ap.add_argument(
        '--jitter',
        type=float,
        default=0.0,
        help='per-segment time factor 1 +- jitter',
    )
    ap.add_argument(
        '--plan-speed',
        type=float,
        help='Task Manager speed (m/s) like speed:= of the launch files, '
        'default 0.08 (planned with x plan-speed-factor)',
    )
    # [수정 2026-11-18] W10: 안내 속도와 계획 속도 배율
    ap.add_argument(
        '--plan-guide-speed',
        type=float,
        help='Task Manager guide speed (m/s), default 0.05',
    )
    ap.add_argument(
        '--plan-speed-factor',
        type=float,
        help='plan speed factor, default 0.9 (Task Manager default)',
    )
    # [수정 2026-11-18] W6: 계획 구간 지연
    ap.add_argument(
        '--plan-overhead',
        type=float,
        help='per-segment delay the Task Manager plans with (s), default 0',
    )
    ap.add_argument(
        '--baseline',
        default='',
        help='"<scheduler> <planner>" compared seed by seed',
    )
    ap.add_argument(
        '--check',
        action='store_true',
        help='pass / fail per pair, exit code 1 if any pair fails',
    )
    ap.add_argument(
        '--map-id', default='', help='measured map for --scenario moves'
    )
    ap.add_argument(
        '--max-t',
        type=float,
        default=0.0,
        help='max simulated time (s), default 1500 (3000 measured)',
    )
    ap.add_argument('--jobs', type=int, default=1, help='parallel processes')
    a = ap.parse_args()
    if a.scenario == MOVES:
        if not a.map_id:
            ap.error('--scenario moves needs --map-id (a measured map)')
        os.environ['FRYBOT_MAP_ID'] = a.map_id
    model = _model_of(a)
    max_t = a.max_t or (1500.0 if a.time_model == 'ideal' else 3000.0)
    pairs = [(s, p) for s in a.schedulers for p in a.planners]
    base = tuple(a.baseline.split()) if a.baseline else None
    if base and base not in pairs:
        pairs.append(base)
    jobs = [
        (
            a.scenario,
            s,
            p,
            k,
            a.robots,
            model,
            a.plan_speed,
            not a.no_standby,
            max_t,
            a.plan_overhead,
            a.plan_guide_speed,
            a.plan_speed_factor,
        )
        for s, p in pairs
        for k in (
            [a.only_seed] if a.only_seed is not None else range(a.seeds)
        )
    ]
    if a.jobs > 1:
        with multiprocessing.Pool(a.jobs) as pool:
            out = pool.map(_job, jobs)
    else:
        out = [_job(j) for j in jobs]
    raw, lists = {}, {}
    for job, (row, values) in zip(jobs, out, strict=True):
        row['seed'] = job[3]
        raw.setdefault((job[1], job[2]), []).append(row)
        lists.setdefault((job[1], job[2]), []).extend(values)
    cols = MOVE_COLS if a.scenario == MOVES else COLS
    rows = []
    for (s, p), rs in raw.items():
        row = dict(
            scheduler=s,
            planner=p,
            finished=f"{sum(r['finished'] for r in rs)}/{len(rs)}",
        )
        for c in cols[3:] + EXTRA_COLS:
            # [수정 2026-11-18] W4: 위치 문자열 열은 평균 내지 않음
            if c == 'plan_fail_long_at':
                continue
            vals = [r[c] for r in rs if r[c] == r[c]]
            row[c] = (
                (
                    min(vals)
                    if c == 'min_sep'
                    else round(sum(vals) / len(vals), 2)
                )
                if vals
                else float('nan')
            )
        rows.append(row)
    w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    _factor = 0.9 if a.plan_speed_factor is None else a.plan_speed_factor
    print(
        f'scenario={a.scenario} seeds={a.seeds}  (times in s, dist in m, '
        'min_sep = closest robot centres in m)'
    )
    print(
        f'time model={model.name} overhead={model.overhead:g}s '
        f'speed={model.speed:g}m/s jitter={model.jitter:g}'
        # [수정 2026-11-18] W10: 계획 속도 = 일반·안내 속도 x 배율
        f' plan_speed={(a.plan_speed or 0.08) * _factor:g}m/s'
        f' plan_guide_speed={(a.plan_guide_speed or 0.05) * _factor:g}m/s'
        f' plan_overhead={a.plan_overhead or 0.0:g}s'
        + (f' map={a.map_id}' if a.map_id else '')
    )
    print('  '.join(c.ljust(w[c]) for c in cols))
    for r in rows:
        print('  '.join(str(r[c]).ljust(w[c]) for c in cols))
    # [수정 2026-11-18] W3: 분포, 기준선 비교, 통과 판정
    key = 'ratio_med' if a.scenario == MOVES else 'deliver_avg'
    print(
        f'\n분포 (중앙값 [최소~최대], 씨앗 {a.seeds}개)'
        + (f', 기준선 = {" + ".join(base)}' if base else '')
    )
    failed = False
    for (s, p), rs in raw.items():
        name = '명령 소요비' if a.scenario == MOVES else '주문->전달'
        line = (
            f'{s} + {p}: 전체 소요 {_spread([r["makespan"] for r in rs])}, '
            f'{key} {_spread([r[key] for r in rs])}, '
            f'{name} 상위 5% {_p95(lists[(s, p)])}, '
            f'점유 대기 {_spread([r["blocked_wait"] for r in rs])}, '
            f'계획 없는 정지 30초 {sum(r["unplanned30"] for r in rs)}, '
            # [수정 2026-11-18] W11
            f'의도된 대기 20초 {sum(r["intended20"] for r in rs)}, '
            f'의도된 대기 최대 '
            f'{max(r["intended_wait_max"] for r in rs):.0f}s, '
            f'계획 실패 20초 {sum(r["plan_fail_long"] for r in rs)}, '
            f'최소 간격 {min(r["min_sep"] for r in rs):.3f}, '
            f'간격 미달 {sum(r["close_time"] for r in rs):.1f}s, '
            f'ETA 비율 {_spread([r["eta_ratio"] for r in rs])}'
        )
        if base and (s, p) != base:
            by_seed = {r['seed']: r for r in raw[base]}
            diff = [
                r['makespan'] - by_seed[r['seed']]['makespan']
                for r in rs
                if r['seed'] in by_seed
            ]
            better = sum(d < 0 for d in diff)
            line += (
                f', 기준선 대비 전체 소요 차 중앙값 {st.median(diff):+.1f}s '
                f'(나은 씨앗 {better}/{len(diff)})'
            )
        if a.check:
            ok, why = _passes(rs)
            failed |= not ok
            line += ' -> 통과' if ok else f' -> 실패 ({why})'
        print(line)
    if a.csv:
        with open(a.csv, 'w', newline='') as f:
            fields = ['seed'] + cols + EXTRA_COLS
            cw = csv.DictWriter(f, fields, extrasaction='ignore')
            cw.writeheader()
            for rs in raw.values():
                cw.writerows(rs)
        print('saved', a.csv)
    if a.csv_mean:
        with open(a.csv_mean, 'w', newline='') as f:
            cw = csv.DictWriter(f, cols, extrasaction='ignore')
            cw.writeheader()
            cw.writerows(rows)
        print('saved', a.csv_mean)
    if a.check and failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
