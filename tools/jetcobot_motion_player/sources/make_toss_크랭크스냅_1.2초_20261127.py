#!/usr/bin/env python3
"""세로 꽂기 공구로 웍질 (로봇2) → ../motions.json + 맵 URDF 의 웍 관절 값 출력
웍은 손목 끝판에 고정(링크)되어 함께 움직인다. 소켓 윗면 = 웍 좌표 (82, 0, 32), 공구 길이 TOOL."""
import json, os, numpy as np
from scipy.optimize import minimize
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, 'fk.py')).read())
lo = np.radians([-168, -140, -150, -150, -155, -180]); hi = np.radians([168, 140, 150, 150, 160, 180])
TOOL = 37.0                                   # 원판 4 + 목 30 + 꽂이 판 3
W = np.array([150.0, -179.0])                 # 화구 중심 (로봇2 좌표, mm)
TH = np.radians(210)                          # 손잡이(소켓) 방향
SOCK_Z = -10 + 10.06 + 32                     # 소켓 윗면 높이 (로봇 바닥 기준, 테이블 -10)
AX, AZ, TILT, PERIOD, CYC, HZ = 50, 70, -20, 1.2, 5, 20   # TILT 음수 = 앞쪽(먼 쪽)이 아래로
CR_R, CR_LC, CR_LP, CR_LS = 25.0, 100.0, 40.0, 42.0   # 크랭크 반지름, 크랭크 중심→지지점, 지지점 위치, 손잡이 끝→소켓 (mm)
LIFT0 = 8                                     # 웍질 전에 화구에서 살짝 띄우는 높이
def RZ(a): c, s = np.cos(a), np.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
def RY(a): c, s = np.cos(a), np.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
def H(R, p): M = np.eye(4); M[:3, :3] = R; M[:3, 3] = p; return M
T_wf = H(np.diag([1., -1, -1]), [82, 0, 32 + TOOL])          # 웍 → 끝판
def wok_pose(d, h, t):                        # 소켓 윗면을 중심으로 앞쪽을 t 만큼 들어 올림
    u = np.array([np.cos(TH), np.sin(TH), 0]); sc = np.array([*W, SOCK_Z]) + 82 * u
    return H(np.eye(3), sc + u * d + [0, 0, h]) @ H(RZ(TH) @ RY(t), [0, 0, 0]) @ H(np.eye(3), [-82, 0, -32])
def err(q, T):
    F = fk(q)['joint6_flange']; return np.sum((F[:3, 3] * 1000 - T[:3, 3]) ** 2) * 1e-2 + np.sum((F[:3, :3] - T[:3, :3]) ** 2) * 10
def ik(T, seed):
    r = minimize(err, seed, args=(T,), method='BFGS', options={'gtol': 1e-10}); return r.x, r.fun
# 시작 자세: 여러 출발점 중 관절 여유가 가장 큰 것
T0 = wok_pose(0, 0, 0) @ T_wf; rng = np.random.default_rng(0); best = None
for k in range(60):
    q, f = ik(T0, rng.uniform(lo, hi) * 0.7)
    if f < 1e-4 and np.all(q > lo) and np.all(q < hi):
        m = np.min(np.minimum(q - lo, hi - q)[:5])
        if best is None or m > best[0]: best = (m, q)
q = best[1]; Q = []
n = int(PERIOD * CYC * HZ)
# 크랭크 웍질 (참고 영상의 웍 볶음 기계): 손잡이가 고정 지지점 P 를 지나 미끄러지고, 손잡이 끝 C 는 크랭크 원을 돎
#   웍 쪽 평면 좌표 x = 손잡이 쪽(+, 로봇 쪽), z = 위. 소켓 S 는 C 에서 손잡이를 따라 CR_LS 떨어진 점 (C 와 P 사이)
#   → 앞으로 밀며 앞쪽 숙임 → 뒤로 당기며 앞쪽 들림(튕김). 화구에 안 닿게 전체를 CR_DZ 띄움 (자동 계산)
import sys; sys.path.insert(0, HERE); from clearance import gap
def crank_xyz(th):
    P = np.array([CR_LP, 0.0]); C = np.array([CR_LP + CR_LC + CR_R * np.cos(th), CR_R * np.sin(th)])
    e = (C - P) / np.linalg.norm(C - P); S = C - CR_LS * e
    return S, -np.arctan2(e[1], e[0])
_th = np.linspace(0, 2 * np.pi, 48, endpoint=False); _S = np.array([crank_xyz(t)[0] for t in _th])
_xc, _zmin = _S[:, 0].mean(), _S[:, 1].min()
def crank_pose(th, dz=None):
    S, t = crank_xyz(th); return (S[0] - _xc, (CR_DZ if dz is None else dz) + S[1] - _zmin, t)
CR_DZ = max(max(0.0, 1.0 - gap(wok_pose(*crank_pose(t, 0.0)), W)) for t in _th)
print('화구에 안 닿게 띄운 높이 %.0f mm' % CR_DZ)
SNAP = 0.6                                        # 튕기기(뒤로 당기며 앞쪽 들기, θ 180~360°) 반 바퀴를 빠르게: 0 = 같은 속도, 0.6 = 시간의 1/3
def snap(s): return s + SNAP * np.sin(s - 1.5 * np.pi)
TH0 = np.pi / 2                                   # 시작 위상: 맨 아래(앞으로 밀기 직전)
ramp_k = [(1 - np.cos(np.pi * k / HZ)) / 2 for k in range(HZ + 1)]     # 1초 동안 시작 자세로
p0 = crank_pose(TH0)
poses = [tuple(np.array(p0) * k) for k in ramp_k]
for i in range(1, n + 1):
    poses.append(crank_pose(snap(TH0 + 2 * np.pi * i / (PERIOD * HZ))))
poses += [tuple(np.array(p0) * k) for k in ramp_k[::-1][1:]]
for d, h, t in poses:
    TT = wok_pose(d, h, t) @ T_wf
    q, f = ik(TT, q); assert f < 1e-4, f; Q.append(q)
Q = np.array(Q); assert np.all(Q > lo) and np.all(Q < hi)
marg = np.degrees(np.min(np.minimum(Q - lo, hi - Q)[:, :5])); jump = np.degrees(np.max(np.abs(np.diff(Q, axis=0))))
print('시작', np.degrees(Q[0]).round(1), '최소 관절 여유 %.0f°' % marg, '한 칸 최대 변화 %.1f°' % jump)
# 처음 2초 정지 + 웍질 + 끝 정지
hold = [Q[0]] * (2 * HZ); R2 = np.degrees(np.vstack([hold, Q, [Q[-1]] * HZ])).round(3).tolist()
R1 = [[0.0] * 6] * len(R2)
steps = [[0.0, '웍 놓인 자세', 1, 2], [2.0, '웍질 3번', 2, 2]]
M = {"joints": ["joint2_to_joint1", "joint3_to_joint2", "joint4_to_joint3", "joint5_to_joint4", "joint6_to_joint5", "joint6output_to_joint6"],
     "speed": 20, "sequences": [{"name": "웍질 (세로 꽂기 공구)", "hz": HZ, "duration": len(R2) / HZ, "robot1": R1, "robot2": R2, "steps": steps, "n_steps": 2}]}
json.dump(M, open(os.path.join(HERE, '..', 'motions.json'), 'w'), ensure_ascii=False)
T_fw = np.linalg.inv(T_wf); print('웍 관절 (끝판 기준) xyz', (T_fw[:3, 3] / 1000).round(4))
