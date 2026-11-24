"""Baseline: every robot takes its own shortest path. No time coordination - conflicts are only
resolved at run time by the node locks of the traffic layer (wait, then re-route around blockers).

[수정 2026-11-18] W6: 시각을 계획하지 않으므로(Step 시각 0) 구간
지연(PlanRequest.overhead)을 쓰지 않음. 경로는 거리 기준 최단 경로 그대로.
"""
import heapq
from .base import PathPlanner, Step, INF


class IndependentAStarPlanner(PathPlanner):
    name = 'independent_astar'
    coordinated = False
    description = '기준선: 로봇별 최단 경로 A* + 실행 중 구역 점유(락) 대기'

    def plan(self, graph, req, table):
        start, goal = req.start, req.goal
        h = graph.sp_from(goal)
        if start not in h:
            return None
        g, parent = {start: 0.0}, {start: None}
        pq = [(h[start], start)]
        while pq:
            _, u = heapq.heappop(pq)
            if u == goal:
                break
            for w, d in graph.adj[u]:
                if w in req.blocked:
                    continue
                nd = g[u] + d
                if nd < g.get(w, INF):
                    g[w], parent[w] = nd, u
                    heapq.heappush(pq, (nd + h.get(w, INF), w))
        if goal not in parent:
            return None
        seq, n = [], goal
        while n is not None:
            seq.append(n)
            n = parent[n]
        seq.reverse()
        return [Step(n, 0.0, 0.0) for n in seq]
