"""젯코봇 동작 공유 라이브러리 — 주피터에서 `from motion_lib import *` 로 사용

동작 파일 형식 (motions/*.json)
  ROS2 trajectory_msgs/JointTrajectory 와 같은 구조 + 우리 정보(이름·로봇·상태 등)
  - joint_names : 관절 이름 6개 (mycobot_280_m5 URDF)
  - points[].positions        : 라디안 6개
  - points[].time_from_start  : {"sec": 정수, "nanosec": 정수}
  실제 로봇(pymycobot)은 '도' 단위를 쓰므로 load 할 때 자동으로 바꿈.

주요 함수
  list_motions()                      동작 목록
  show(이름)                          관절 그래프
  connect()                           실제 로봇 연결 (pymycobot MyCobot280)
  play(이름, where="real"|"rviz")     재생
  play_all([이름, ...])               여러 동작 차례로
  record(이름, seconds=10)            손으로 따기 → motions/ 에 저장
  stop()                              비상 정지
"""
import datetime as _dt
import glob
import json
import math
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MOTION_DIR = os.path.join(ROOT, "motions")

JOINT_NAMES = ["joint2_to_joint1", "joint3_to_joint2", "joint4_to_joint3",
               "joint5_to_joint4", "joint6_to_joint5", "joint6output_to_joint6"]
# myCobot 280 관절 한계 (도) — 벗어나면 로봇이 명령을 무시함
ANGLE_MIN = [-168, -135, -150, -145, -165, -180]
ANGLE_MAX = [168, 135, 150, 145, 165, 180]

mc = None          # connect() 가 채움


# ───────────────────────── 파일 읽기·쓰기 ─────────────────────────
def _files():
    return sorted(glob.glob(os.path.join(MOTION_DIR, "*.json")))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find(name):
    """이름(또는 파일 이름, 앞부분, 번호)으로 동작 파일 찾기"""
    fs = _files()
    if isinstance(name, int):
        return fs[name - 1]
    if os.path.isfile(name):
        return name
    for p in fs:
        if _read(p)["name"] == name or os.path.basename(p) in (name, name + ".json"):
            return p
    hits = [p for p in fs if name in _read(p)["name"] or name in os.path.basename(p)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"'{name}' 동작이 없습니다. list_motions() 로 이름을 확인하세요.")
    raise ValueError(f"'{name}' 에 맞는 동작이 {len(hits)}개입니다: " + ", ".join(_read(p)["name"] for p in hits))


def load(name):
    """동작 → (정보 dict, [[시간초, J1..J6 도], ...])"""
    m = _read(find(name))
    pts = []
    for p in m["points"]:
        t = p["time_from_start"]
        sec = t["sec"] + t["nanosec"] * 1e-9 if isinstance(t, dict) else float(t)
        pts.append([round(sec, 4)] + [round(math.degrees(r), 2) for r in p["positions"]])
    return m, pts


def slug(name):
    s = re.sub(r"[()\[\]{}]", "", name)
    s = re.sub(r"[\s/\\:*?\"<>|,]+", "_", s).strip("_")
    return s.replace("×", "x")


def save(name, points_deg, robot="", made_by="손으로 따기", status="시험", author="", notes="",
         play_hint=None, extra=None, overwrite=False):
    """[[시간, J1..J6 도], ...] → motions/<이름>.json (JointTrajectory 구조)"""
    os.makedirs(MOTION_DIR, exist_ok=True)
    path = os.path.join(MOTION_DIR, slug(name) + ".json")
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"{os.path.basename(path)} 이 이미 있습니다. 다른 이름을 쓰거나 overwrite=True")
    t0 = points_deg[0][0]
    pts = []
    for p in points_deg:
        t = max(0.0, p[0] - t0)
        sec = int(t)
        pts.append({"positions": [round(math.radians(a), 5) for a in p[1:7]],
                    "time_from_start": {"sec": sec, "nanosec": int(round((t - sec) * 1e9))}})
    m = {
        "format": "trajectory_msgs/JointTrajectory (+ meta)",
        "name": name, "robot": robot, "made_by": made_by, "status": status,
        "author": author or os.environ.get("USER", ""),
        "created": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "notes": notes,
        "play_hint": play_hint or {"speed": 80, "lead": 0.12, "hz": 30},
        **(extra or {}),
        "joint_names": JOINT_NAMES,
        "points": pts,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    print(f"저장: motions/{os.path.basename(path)}  ({len(pts)}점, {points_deg[-1][0] - t0:.1f}초)")
    try:
        from make_index import make_index
        make_index(quiet=True)
        print("목록 페이지(MOTIONS.md)도 새로 만들었습니다.")
    except Exception as e:                      # matplotlib 없음 등 — 저장은 이미 됨
        print("(목록 페이지는 못 만듦:", e, ")")
    return path


def list_motions():
    """동작 목록 출력 (번호로도 play(2) 처럼 고를 수 있음)"""
    fs = _files()
    if not fs:
        print("motions/ 에 동작이 없습니다.")
    for i, p in enumerate(fs, 1):
        m, pts = load(p)
        print(f"{i:2d}. [{m.get('status', '')}] {m['name']}  — {pts[-1][0]:.1f}초, {m.get('robot', '')}")


def _korean_font(plt):
    from matplotlib import font_manager
    for fam in ("NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP", "UnDotum"):
        try:
            font_manager.findfont(fam, fallback_to_default=False)
            plt.rcParams["font.family"] = fam
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False


def show(name):
    """관절 각도 그래프 (J1~J6, 도)"""
    import matplotlib.pyplot as plt
    _korean_font(plt)
    m, pts = load(name)
    t = [p[0] for p in pts]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for j in range(6):
        ax.plot(t, [p[j + 1] for p in pts], label=f"J{j + 1}")
    ax.set_xlabel("시간 (초)")
    ax.set_ylabel("각도 (°)")
    ax.set_title(m["name"])
    ax.grid(alpha=0.3)
    ax.legend(ncol=6, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    fig.tight_layout()
    plt.show()
    print(f"만든 방법: {m.get('made_by', '')}\n상태: {m.get('status', '')}   메모: {m.get('notes', '')}")


# ───────────────────────── 실제 로봇 ─────────────────────────
def connect(port="/dev/ttyJETCOBOT", baud=1000000, fake=False):
    """실제 로봇 연결. fake=True 면 가짜 로봇(움직이지 않고 출력만) — 재생 연습용"""
    global mc
    if fake:
        mc = FakeCobot()
    else:
        from pymycobot.mycobot280 import MyCobot280
        mc = MyCobot280(port, baud)
        time.sleep(0.5)
    print("연결됨:", "가짜 로봇" if fake else port, " 현재 각도:", mc.get_angles())
    return mc


def _send(angles, speed):
    """이동 명령은 응답을 기다리지 않게 _async=True (pymycobot 4.x 는 기본값이 기다림 → 뚝뚝 끊김)"""
    try:
        return mc.send_angles(angles, speed, _async=True)
    except TypeError:                         # pymycobot 3.x 는 _async 인자가 없음
        return mc.send_angles(angles, speed)


def _wait(target, timeout=20):
    t0 = time.time()
    time.sleep(0.4)
    prev, still = None, 0
    while time.time() - t0 < timeout:
        cur = mc.get_angles()
        if isinstance(cur, list) and len(cur) == 6:
            if max(abs(a - b) for a, b in zip(cur, target)) < 2.0:
                return True
            if prev and max(abs(a - b) for a, b in zip(cur, prev)) < 0.3:
                still += 1
                if still >= 3:
                    return True
            else:
                still = 0
            prev = cur
        time.sleep(0.2)
    return False


def _check_limits(pts):
    bad = []
    for p in pts:
        for j, (a, lo, hi) in enumerate(zip(p[1:7], ANGLE_MIN, ANGLE_MAX), 1):
            if not lo <= a <= hi:
                bad.append(f"{p[0]:.2f}초 J{j} {a:.1f}° (허용 {lo}~{hi}°)")
    if bad:
        raise ValueError("관절 한계를 벗어나는 점이 있어 재생하지 않습니다:\n  " + "\n  ".join(bad[:5]))


def play_real(name, speed=None, rate=1.0, lead=None, hz=None):
    """실제 로봇으로 재생.
    - 먼저 시작 자세로 천천히(속도 20) 이동 → 초당 hz번 '조금 앞(lead초) 각도'를 보냄
    - rate: 0.5 = 절반 속도로 천천히 (처음엔 0.5 추천)
    - 멈추기: 주피터 ■(커널 중지) 버튼 → 자동으로 mc.stop()
    """
    if mc is None:
        raise RuntimeError("먼저 connect() 로 로봇을 연결하세요.")
    m, pts = load(name)
    hint = m.get("play_hint", {})
    speed = int(speed or hint.get("speed", 80))
    lead = float(hint.get("lead", 0.12) if lead is None else lead)
    hz = float(hz or hint.get("hz", 30))
    _check_limits(pts)
    ts = [p[0] for p in pts]
    angs = [p[1:7] for p in pts]
    dur = ts[-1]

    def angle_at(t):
        if t >= dur:
            return angs[-1]
        if t <= 0:
            return angs[0]
        i = max(0, next(k for k in range(1, len(ts)) if ts[k] >= t) - 1)
        f = (t - ts[i]) / max(ts[i + 1] - ts[i], 1e-6)
        return [round(a + (b - a) * f, 2) for a, b in zip(angs[i], angs[i + 1])]

    print(f"▶ {m['name']}  ({dur:.1f}초 → 실제 {dur / rate:.1f}초, 속도 {speed}, {hz:g}Hz, 앞당김 {lead}초)")
    try:
        mc.focus_all_servos()
        time.sleep(0.3)
        print("  시작 자세로 이동 (속도 20)…")
        _send(angs[0], 20)
        _wait(angs[0])
        prev_mode = mc.get_fresh_mode()
        if prev_mode != 1:
            mc.set_fresh_mode(1)          # 새 명령이 오면 바로 그쪽으로 (줄 세우지 않음)
            time.sleep(0.05)
        try:
            period, t_start = 1.0 / hz, time.time()
            nxt, sent = t_start, 0
            while True:
                t = (time.time() - t_start) * rate
                _send(angle_at(t + lead * rate), speed)
                sent += 1
                if t >= dur:
                    break
                nxt += period
                w = nxt - time.time()
                if w > 0:
                    time.sleep(w)
                else:
                    nxt = time.time()
            real = time.time() - t_start
            print(f"  전송 {sent}번 / {real:.1f}초 = {sent / max(real, 1e-6):.0f}Hz")
        finally:
            if isinstance(prev_mode, int) and prev_mode in (0, 1) and prev_mode != 1:
                mc.set_fresh_mode(prev_mode)
        _wait(angs[-1])
        print("■ 재생 완료")
    except KeyboardInterrupt:
        stop()
        print("■ 중단했습니다 (mc.stop)")


def stop():
    """비상 정지"""
    if mc is not None:
        mc.stop()
        print("정지 명령 보냄")


def record(name, seconds=10, interval=0.1, robot="", notes="", author=""):
    """손으로 따기: 서보를 풀고 → 3초 뒤부터 seconds초 동안 interval초마다 각도 기록 → motions/ 에 저장
    도중에 그만두려면 ■(커널 중지) — 거기까지 기록한 것을 저장함"""
    if mc is None:
        raise RuntimeError("먼저 connect() 로 로봇을 연결하세요.")
    mc.release_all_servos()
    print("서보 풀림: 팔을 손으로 잡으세요.")
    for n in (3, 2, 1):
        print(f"{n}…")
        time.sleep(1)
    print(f"● 녹화 시작 ({seconds}초)")
    pts, t0 = [], time.time()
    try:
        while time.time() - t0 < seconds:
            tick = time.time()
            a = mc.get_angles()
            if isinstance(a, list) and len(a) == 6:
                pts.append([round(tick - t0, 3)] + a)
            time.sleep(max(0.0, interval - (time.time() - tick)))
    except KeyboardInterrupt:
        print("(중간에 멈춤)")
    mc.focus_all_servos()
    print(f"■ 녹화 끝: {len(pts)}점")
    if len(pts) < 2:
        print("점이 너무 적어 저장하지 않았습니다.")
        return None
    return save(name, pts, robot=robot, made_by="손으로 따기 (record)", status="시험", notes=notes,
                author=author, play_hint={"speed": 50, "lead": 0.12, "hz": 30})


# ───────────────────────── RViz ─────────────────────────
def play_rviz(name, rate=1.0, loop=False):
    """RViz 에서 재생 (ROS2 Jazzy 필요). 처음엔 RViz 창이 열림 — 창을 닫으면 끝.
    주피터 커널에 rclpy 가 없어도 되도록 별도 프로그램(tools/play_rviz.py)으로 실행"""
    path = find(name)
    cmd = (f"source /opt/ros/jazzy/setup.bash && python3 '{os.path.join(HERE, 'play_rviz.py')}' "
           f"'{path}' --rate {rate}" + (" --loop" if loop else ""))
    print("RViz 재생:", os.path.basename(path))
    return subprocess.Popen(["bash", "-c", cmd])


# ───────────────────────── 공통 ─────────────────────────
def play(name, where="real", **kw):
    """where="real" (실제 로봇) 또는 "rviz" """
    if where == "rviz":
        return play_rviz(name, **{k: v for k, v in kw.items() if k in ("rate", "loop")})
    return play_real(name, **kw)


def play_all(names, where="real", pause=1.0, **kw):
    """여러 동작을 차례로 (실제 로봇). RViz 는 하나씩 play(..., where='rviz')"""
    if where == "rviz":
        raise ValueError("RViz 는 play_rviz.py 에 파일 여러 개를 줄 수 있습니다: play_rviz_many([...])")
    for n in names:
        play_real(n, **kw)
        time.sleep(pause)


def play_rviz_many(names, rate=1.0):
    paths = " ".join(f"'{find(n)}'" for n in names)
    cmd = f"source /opt/ros/jazzy/setup.bash && python3 '{os.path.join(HERE, 'play_rviz.py')}' {paths} --rate {rate}"
    return subprocess.Popen(["bash", "-c", cmd])


class FakeCobot:
    """로봇 없이 재생 흐름을 시험하는 가짜 로봇 (보낸 명령을 기억만 함)"""
    def __init__(self):
        self.angles, self.sent, self.mode = [0.0] * 6, 0, 0

    def get_angles(self):
        return list(self.angles)

    def send_angles(self, a, speed, _async=False):
        self.angles = list(a)
        self.sent += 1

    def get_fresh_mode(self):
        return self.mode

    def set_fresh_mode(self, m):
        self.mode = m

    def focus_all_servos(self):
        pass

    def release_all_servos(self):
        pass

    def stop(self):
        pass
