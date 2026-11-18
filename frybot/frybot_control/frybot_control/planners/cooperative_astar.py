"""Cooperative A* (Silver 2005): prioritized space-time A* on a fixed time grid with a reservation table."""
import heapq
import math
from .base import PathPlanner, Step, INF, start_interval_end


class CooperativeAStarPlanner(PathPlanner):
    name = 'cooperative_astar'
    coordinated = True
    description = '협조 A* (시간 격자 0.5초 + 예약 테이블)'

    def __init__(self, dt=0.5, horizon=600):
        self.dt, self.horizon = dt, horizon

    def plan(self, graph, req, table):
        start, goal, t0, v, dt = req.start, req.goal, req.t0, req.speed, self.dt
        h = graph.sp_from(goal)
        if start not in h:
            return None
        s_end = start_interval_end(table, start, t0)

        def free(n, a, b):
            if n == start and b <= s_end:
                return True
            return table.is_free(n, a, b)

        g = {(start, 0): 0}
        parent = {(start, 0): None}
        pq = [(h[start] / v, 0, start)]
        while pq:
            _, k, u = heapq.heappop(pq)
            t = t0 + k * dt
            if u == goal:
                hold = req.goal_hold
                if (hold == INF and table.first_block_after(u, t) == INF and free(u, t, t + 1)) or \
                   (hold < INF and free(u, t, t + hold)):
                    return self._path(parent, (u, k), t0, dt, req)
            if k >= self.horizon:
                continue
            cand = []
            if free(u, t, t + dt):
                cand.append((u, k + 1))                                  # wait
            for w, d in graph.adj[u]:
                if w in req.blocked or w not in h:
                    continue
                # [수정 2026-11-18] W6: 구간 지연 포함
                n = max(1, math.ceil(req.segment_time(d) / dt))
                if free(w, t, t + n * dt) and free(u, t, t + n * dt):
                    cand.append((w, k + n))
            for (w, k2) in cand:
                if k2 < g.get((w, k2), 1 << 30):
                    g[(w, k2)] = k2
                    parent[(w, k2)] = (u, k)
                    heapq.heappush(pq, (k2 * dt + h[w] / v, k2, w))
        return None

    @staticmethod
    def _path(parent, key, t0, dt, req):
        seq = []
        while key is not None:
            seq.append(key)
            key = parent[key]
        seq.reverse()
        # [수정 2026-11-17] 결과를 쓰지 않던 첫 번째 steps 루프와
        # 빈 반복문, 쓰지 않는 idx 삭제. 아래 루프가 같은 값을 만듦
        # leave node i at the last time we were still there
        out = []
        for n, k in seq:
            t = t0 + k * dt
            if out and out[-1].node == n:
                out[-1].depart = t             # waiting in place
            else:
                out.append(Step(n, t, t))
        out[-1].depart = out[-1].arrive + (req.goal_hold if req.goal_hold < INF else 0.0)
        return out
