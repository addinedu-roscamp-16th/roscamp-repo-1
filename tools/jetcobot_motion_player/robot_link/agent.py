"""
JetCobot 쪽에서 실행되는 에이전트.
PC의 cobot_tester.py가 SSH로 이 코드를 보내 실행하며, 로봇에 파일을 설치하지 않는다.
stdin으로 JSON 명령을 한 줄씩 받고, stdout으로 JSON 메시지를 한 줄씩 보낸다.
"""
import io
import json
import queue
import subprocess
import sys
import threading
import time
import traceback

PORT = "/dev/ttyJETCOBOT"
BAUD = 1000000

_real_out = sys.stdout
_out_lock = threading.Lock()


def emit(**msg):
    with _out_lock:
        _real_out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        _real_out.flush()


class _Stream(io.TextIOBase):
    def __init__(self, kind):
        self.kind = kind

    def write(self, text):
        if text:
            emit(type=self.kind, text=text)
        return len(text)

    def flush(self):
        pass


sys.stdout = _Stream("out")
sys.stderr = _Stream("err")

mc = None
stop_flag = threading.Event()
jobs = queue.Queue()
ns = {"time": time}


def need_robot():
    if mc is None:
        raise RuntimeError("로봇이 연결되지 않았습니다. 먼저 '연결'을 누르세요.")


def wait_done(target=None, timeout=30):
    """움직임이 끝날 때까지 대기. target(각도 6개)에 도달하거나 각도가 멈추면 끝."""
    need_robot()
    show("# 도착할 때까지 대기 (mc.get_angles()로 0.2초마다 확인)")
    t0 = time.time()
    time.sleep(0.4)
    prev, still = None, 0
    while time.time() - t0 < timeout:
        if stop_flag.is_set():
            return "stopped"
        cur = mc.get_angles()
        if isinstance(cur, list) and len(cur) == 6:
            if target and max(abs(a - b) for a, b in zip(cur, target)) < 2.0:
                return "reached"
            if prev and max(abs(a - b) for a, b in zip(cur, prev)) < 0.3:
                still += 1
                if still >= 3:
                    return "settled"
            else:
                still = 0
            prev = cur
        time.sleep(0.2)
    return "timeout"


def show(code):
    """실제로 실행하는 명령을 PC 터미널에 표시"""
    emit(type="code", text=code)

# 관절 한계 (myCobot 280). 현재 각도가 이 범위를 벗어나 있으면 로봇이 이동 명령을 무시함
ANGLE_MIN = [-168, -135, -150, -145, -165, -180]
ANGLE_MAX = [168, 135, 150, 145, 165, 180]


def limits_ok(target=None):
    """이동 전에 현재 각도와 목표 각도가 관절 한계 안인지 확인. 벗어나면 안내를 출력하고 False"""
    cur = call("get_angles")
    bad = []
    if isinstance(cur, list) and len(cur) == 6:
        for j, (a, lo, hi) in enumerate(zip(cur, ANGLE_MIN, ANGLE_MAX), 1):
            if not lo <= a <= hi:
                bad.append(f"J{j} 현재 {a:.1f}° (허용 {lo}~{hi}°)")
    if target:
        for j, (a, lo, hi) in enumerate(zip(target, ANGLE_MIN, ANGLE_MAX), 1):
            if not lo <= a <= hi:
                bad.append(f"J{j} 목표 {a:.1f}° (허용 {lo}~{hi}°)")
    if not bad:
        return True
    print("⚠ 관절 한계를 벗어나 있어 로봇이 명령을 무시합니다. 이동하지 않았습니다.")
    for b in bad:
        print("   -", b)
    js = [int(b[1]) for b in bad if "현재" in b]
    if js:
        j = js[0]
        print(f"   해결: exec에서 mc.release_servo({j}) → J{j}를 손으로 한계 안쪽으로 돌림 "
              f"→ mc.focus_servo({j}) 후 다시 시도")
    raise Abort("관절 한계 밖이라 이동하지 않았습니다.")



# 이동 명령은 응답을 기다리지 않고 보냄(_async=True).
# pymycobot 4.x의 MyCobot280은 이동 명령마다 응답을 최대 0.5초×3회 기다리고 다시 보내서
# 연속 동작이 뚝뚝 끊기고, 그동안 시리얼 잠금을 쥐고 있어 '정지'도 늦게 먹힘.
ASYNC_MOVES = {"send_angles", "send_coords", "send_angle"}
NO_ASYNC = []


def call(fn, *args):
    """mc.fn(*args)를 터미널에 표시하고 실행"""
    kw = {"_async": True} if fn in ASYNC_MOVES and not NO_ASYNC else {}
    extra = ", _async=True" if kw else ""
    show(f"mc.{fn}({', '.join(repr(a) for a in args)}{extra})")
    try:
        return getattr(mc, fn)(*args, **kw)
    except TypeError as e:
        # pymycobot 3.x(aa1f 등)는 _async 인자가 없음 → 빼고 다시 보냄
        if kw and "_async" in str(e):
            NO_ASYNC.append(True)
            return getattr(mc, fn)(*args)
        raise


class Abort(Exception):
    """사용자에게 보여줄 짧은 실패 사유 (트레이스백 없이 표시)"""


def send_fast(angles, speed):
    """화면 표시 없이 각도 전송 (궤적 재생용). pymycobot 3.x는 _async 인자가 없음"""
    if NO_ASYNC:
        return mc.send_angles(angles, speed)
    try:
        return mc.send_angles(angles, speed, _async=True)
    except TypeError as e:
        if "_async" not in str(e):
            raise
        NO_ASYNC.append(True)
        return mc.send_angles(angles, speed)


def state():
    need_robot()
    emit(type="state", angles=call("get_angles"), coords=call("get_coords"))


def do_connect(_):
    global mc
    try:
        r = subprocess.run(["fuser", PORT], capture_output=True, text=True)
        pids = r.stdout.split()
        if pids:
            print(f"[주의] 다른 프로그램(PID {' '.join(pids)})이 {PORT}를 사용 중입니다. "
                  "주피터 노트북 커널이면 종료 후 다시 연결하세요.")
    except Exception:
        pass
    show("from pymycobot.mycobot280 import MyCobot280")
    from pymycobot.mycobot280 import MyCobot280
    from pymycobot.genre import Angle, Coord
    show(f"mc = MyCobot280({PORT!r}, {BAUD})")
    mc = MyCobot280(PORT, BAUD)
    show("mc.thread_lock = True")
    mc.thread_lock = True
    time.sleep(0.5)
    if call("is_power_on") != 1:
        print("전원이 꺼져 있어 power_on() 실행")
        call("power_on")
        time.sleep(0.5)
    ns.update(mc=mc, Angle=Angle, Coord=Coord, wait=wait_done)
    print(f"연결됨: {PORT} @ {BAUD}")
    state()


def do_disconnect(_):
    global mc
    if mc is None:
        return
    if mc is not None:
        try:
            show("mc._serial_port.close()")
            mc._serial_port.close()
        except Exception:
            pass
    mc = None
    ns.pop("mc", None)
    print("연결 해제됨")


def do_state(_):
    state()


def do_home(c):
    need_robot()
    target = [0, 0, 0, 0, 0, 0]
    if not limits_ok():
        return
    call("send_angles", target, c["speed"])
    print("결과:", wait_done(target))
    state()


def do_angles(c):
    need_robot()
    if not limits_ok(c["values"]):
        return
    call("send_angles", c["values"], c["speed"])
    print("결과:", wait_done(c["values"]))
    state()


def do_coords(c):
    need_robot()
    if not limits_ok():
        return
    call("send_coords", c["values"], c["speed"], 0)
    print("결과:", wait_done())
    state()


def do_gripper(c):
    need_robot()
    call("set_gripper_value", int(c["value"]), c["speed"])
    time.sleep(0.8)
    print("그리퍼 값:", call("get_gripper_value"))


def do_release(_):
    need_robot()
    call("release_all_servos")
    print("서보 풀림: 손으로 움직일 수 있습니다.")


def do_focus(_):
    need_robot()
    call("focus_all_servos")
    print("서보 고정됨")
    state()


def do_play(c):
    need_robot()
    poses = c["poses"]
    if not limits_ok():
        return
    for p in poses:
        if not limits_ok(p["angles"]):
            print(f"   (자세 '{p['name']}')")
            return
    for rep in range(c.get("repeat", 1)):
        for i, p in enumerate(poses):
            if stop_flag.is_set():
                print("재생 중단")
                return
            print(f"[{rep + 1}회차] {i + 1}/{len(poses)} {p['name']}")
            call("send_angles", p["angles"], c["speed"])
            r = wait_done(p["angles"])
            if r == "stopped":
                print("재생 중단")
                return
    print("재생 완료")
    state()


def do_exec(c):
    src = c["code"]
    try:
        code = compile(src, "<console>", "eval")
    except SyntaxError:
        exec(compile(src, "<console>", "exec"), ns)
    else:
        r = eval(code, ns)
        if r is not None:
            print(repr(r))



rec_stop = threading.Event()


def do_record(c):
    """손으로 움직이는 동안 일정 간격으로 각도를 기록 (시연 녹화)"""
    need_robot()
    interval = float(c.get("interval", 0.1))
    rec_stop.clear()
    if c.get("release", True):
        call("release_all_servos")
        print("서보 풀림: 팔을 손으로 잡으세요.")
    for n in (3, 2, 1):
        if stop_flag.is_set() or rec_stop.is_set():
            print("녹화 취소")
            return
        print(f"{n}…")
        time.sleep(1)
    print("● 녹화 시작! 손으로 움직이세요. 끝나면 '녹화 끝'을 누르세요.")
    show(f"# {interval}초마다 mc.get_angles()로 기록")
    pts, t0, last_report = [], time.time(), 0
    while not (stop_flag.is_set() or rec_stop.is_set()):
        tick = time.time()
        a = mc.get_angles()
        if isinstance(a, list) and len(a) == 6:
            pts.append([round(tick - t0, 3)] + a)
        if tick - last_report >= 1:
            last_report = tick
            emit(type="rec_progress", n=len(pts), sec=round(tick - t0, 1))
        time.sleep(max(0.0, interval - (time.time() - tick)))
    print(f"■ 녹화 끝: {len(pts)}개 점, {pts[-1][0] if pts else 0:.1f}초")
    emit(type="traj", interval=interval, points=pts)


PLAY_MODES = {
    "lead": "앞당김 (send_angles, 0.12초 앞 목표)",
    "plain": "옛 방식 (send_angles, 지금 목표)",
    "queue": "대기열 (fresh mode 0, 점을 순서대로)",
    "drag": "관절별 속도 (set_encoders_drag, 시험)",
}


def do_play_traj(c):
    """녹화/생성한 궤적 재생 — 재생 방식(mode)을 골라 비교할 수 있음
    lead : fresh mode 1 + 초당 hz번 send_angles(LEAD초 뒤 각도)  → 모터가 목표에 닿아 감속하는 끊김 줄임 (기본)
    plain: fresh mode 1 + 초당 hz번 send_angles(지금 각도)        → 예전 방식
    queue: fresh mode 0(명령을 줄 세워 차례로 실행) + 저장된 점을 그 시각에 send_angles
    drag : fresh mode 1 + 초당 hz번 set_encoders_drag(엔코더, 관절별 속도 step/s)  — 엔코더 보정(c['cal']) 필요
    """
    need_robot()
    mode = c.get("mode", "lead")
    STREAM_HZ = float(c.get("hz", 30))
    LEAD = float(c.get("lead", 0.12)) if mode in ("lead", "drag") else 0.0
    pts = c["points"]
    if len(pts) < 2:
        raise RuntimeError("점이 너무 적습니다.")
    rate = float(c.get("rate", 1.0))
    speed = int(c["speed"])
    repeat = int(c.get("repeat", 1))
    ts = [p[0] - pts[0][0] for p in pts]
    angs = [p[1:7] for p in pts]
    dur = ts[-1]
    cal = c.get("cal")
    MEAS_HZ = float(c.get("measure_hz", 0) or 0)     # >0: 재생 중 실제 각도를 이 빈도로 읽어 기록 (계획 각도와 비교용)
    meas = []
    if mode == "drag" and not (isinstance(cal, dict) and len(cal.get("slope", [])) == 6):
        raise RuntimeError("관절별 속도 방식은 먼저 '엔코더 보정 측정'을 해야 합니다.")

    def seg(t):
        return max(0, min(len(ts) - 2, next((k for k in range(1, len(ts)) if ts[k] >= t), len(ts) - 1) - 1))

    def angle_at(t):
        if t >= dur:
            return angs[-1]
        if t <= 0:
            return angs[0]
        i = seg(t)
        f = (t - ts[i]) / max(ts[i + 1] - ts[i], 1e-6)
        return [round(a + (b - a) * f, 2) for a, b in zip(angs[i], angs[i + 1])]

    def vel_at(t):
        """관절 속도 °/s (궤적 시간 기준)"""
        if t >= dur or t < 0:
            return [0.0] * 6
        i = seg(t)
        d = max(ts[i + 1] - ts[i], 1e-6)
        return [(b - a) / d for a, b in zip(angs[i], angs[i + 1])]

    def to_enc(a):
        return [int(round(o + s * x)) for x, s, o in zip(a, cal["slope"], cal["offset"])]

    call("focus_all_servos")
    time.sleep(0.3)
    if not limits_ok(angs[0]):
        return
    print("시작 자세로 이동 (속도 20)")
    call("send_angles", angs[0], 20)
    if wait_done(angs[0]) == "stopped":
        return

    want_mode = 0 if mode == "queue" else 1
    prev_mode = call("get_fresh_mode")
    if prev_mode != want_mode:
        call("set_fresh_mode", want_mode)
        time.sleep(0.05)
    if mode == "queue":
        try:
            call("clear_queue")
        except Exception:
            pass
    try:
        if mode == "drag":
            show(f"# 이후 {STREAM_HZ:g}Hz로 mc.set_encoders_drag(엔코더(+{LEAD:g}초 앞), 관절별 속도 step/s) 연속 전송, "
                 f"{dur / rate:.1f}초 × {repeat}회")
        elif mode == "queue":
            show(f"# 이후 저장된 점 {len(pts)}개를 그 시각에 mc.send_angles(각도, {speed}) (fresh mode 0: 차례로 실행)")
        else:
            show(f"# 이후 {STREAM_HZ:g}Hz로 mc.send_angles(보간한 각도" + (f"(+{LEAD:g}초 앞)" if LEAD else "")
                 + f", {speed}) 연속 전송, {dur / rate:.1f}초 × {repeat}회 (_async=True)")
        print(f"  재생 방식: {PLAY_MODES.get(mode, mode)}")
        for rep in range(repeat):
            print(f"▶ {rep + 1}회차 재생")
            t_start = time.time()
            sent, late = 0, 0.0
            if mode == "queue":
                for tk, a in zip(ts, angs):
                    if stop_flag.is_set():
                        print("재생 중단")
                        return
                    wait = t_start + tk / rate - time.time()
                    if wait > 0:
                        time.sleep(wait)
                    send_fast(a, speed)
                    sent += 1
            else:
                period = 1.0 / STREAM_HZ
                nxt = t_start
                meas_every = max(1, int(round(STREAM_HZ / MEAS_HZ))) if MEAS_HZ > 0 else 0
                while True:
                    if stop_flag.is_set():
                        print("재생 중단")
                        return
                    t = (time.time() - t_start) * rate
                    tl = t + LEAD * rate
                    if mode == "drag":
                        sp = [max(1, int(round(abs(v * s) * rate))) for v, s in zip(vel_at(tl), cal["slope"])]
                        mc.set_encoders_drag(to_enc(angle_at(tl)), sp)
                    else:
                        send_fast(angle_at(tl), speed)
                    sent += 1
                    if meas_every and sent % meas_every == 0:
                        a = mc.get_angles()
                        if isinstance(a, list) and len(a) == 6:
                            meas.append([rep, round((time.time() - t_start) * rate, 3)] + a)
                    if t >= dur:
                        break
                    nxt += period                      # 정해진 박자로 (보내는 데 걸린 시간만큼 밀리지 않게)
                    wait = nxt - time.time()
                    if wait > 0:
                        time.sleep(wait)
                    else:
                        late = max(late, -wait)
                        nxt = time.time()
            real = time.time() - t_start
            print(f"  전송 {sent}번 / {real:.1f}초 = {sent / max(real, 1e-6):.0f}Hz"
                  + (f", 최대 지연 {late * 1000:.0f}ms" if late > 0.005 else ""))
            if rep + 1 < repeat and angs[0] != angs[-1]:
                send_fast(angs[0], 20)
                wait_done(angs[0])
    finally:
        if isinstance(prev_mode, int) and prev_mode >= 0 and prev_mode != want_mode:
            call("set_fresh_mode", prev_mode)
    if mode == "drag":
        send_fast(angs[-1], 20)               # 엔코더 반올림 차이 정리
    wait_done(angs[-1])
    print("재생 완료")
    if MEAS_HZ > 0:
        print(f"실제 각도 {len(meas)}개 기록")
        emit(type="measure", points=meas, plan=pts, rate=rate, lead=LEAD, mode=mode)
    state()


def do_enc_cal(c):
    """엔코더 보정 측정: 관절마다 ±10° 천천히 움직여 (각도, 엔코더) 두 쌍을 읽고
    엔코더 = offset + slope × 각도 를 구함 → emit(type='enc_cal')  (관절별 속도 재생 방식에 필요)"""
    need_robot()
    call("focus_all_servos")
    time.sleep(0.3)
    base = call("get_angles")
    if not (isinstance(base, list) and len(base) == 6):
        raise RuntimeError("현재 각도를 읽지 못했습니다.")
    slope, offset = [], []
    for j in range(6):
        if stop_flag.is_set():
            print("측정 중단")
            return
        step = 10 if base[j] + 10 <= ANGLE_MAX[j] - 5 else -10
        pairs = []
        for target in (base[j], base[j] + step):
            a = list(base)
            a[j] = target
            send_fast(a, 15)
            if wait_done(a) == "stopped":
                return
            time.sleep(0.4)
            ang, enc = mc.get_angles(), mc.get_encoders()
            if not (isinstance(ang, list) and isinstance(enc, list) and len(ang) == 6 and len(enc) == 6):
                raise RuntimeError(f"J{j + 1}: 각도/엔코더를 읽지 못했습니다 ({ang}, {enc})")
            pairs.append((ang[j], enc[j]))
        (a0, e0), (a1, e1) = pairs
        if abs(a1 - a0) < 3:
            raise RuntimeError(f"J{j + 1}가 움직이지 않았습니다 ({a0:.1f} → {a1:.1f})")
        s = (e1 - e0) / (a1 - a0)
        slope.append(round(s, 4))
        offset.append(round(e1 - s * a1, 1))
        print(f"  J{j + 1}: 엔코더 = {offset[-1]:g} + {slope[-1]:g} × 각도")
        send_fast(base, 15)
        wait_done(base)
    emit(type="enc_cal", slope=slope, offset=offset)
    print("엔코더 보정 측정 완료")


HANDLERS = {
    "connect": do_connect, "disconnect": do_disconnect, "state": do_state,
    "home": do_home, "angles": do_angles, "coords": do_coords,
    "gripper": do_gripper, "release": do_release, "focus": do_focus,
    "play": do_play, "exec": do_exec,
    "record": do_record, "play_traj": do_play_traj, "enc_cal": do_enc_cal,
}


def worker():
    while True:
        c = jobs.get()
        stop_flag.clear()
        ok, err = True, None
        try:
            HANDLERS[c["cmd"]](c)
        except Abort as e:
            ok, err = False, f"{e}\n"
        except Exception:
            ok, err = False, traceback.format_exc()
        emit(type="done", id=c.get("id"), cmd=c["cmd"], ok=ok, error=err)


def main():
    threading.Thread(target=worker, daemon=True).start()
    emit(type="ready")
    for line in _real_in:
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
        except ValueError:
            continue
        if c.get("cmd") == "record_stop":
            rec_stop.set()
        elif c.get("cmd") == "stop":
            # 정지는 대기열을 거치지 않고 즉시 처리
            stop_flag.set()
            rec_stop.set()
            while not jobs.empty():
                try:
                    jobs.get_nowait()
                except queue.Empty:
                    break
            if mc is not None:
                try:
                    show("mc.stop()")
                    mc.stop()
                except Exception:
                    pass
            emit(type="out", text="■ 정지 명령 전송\n")
        elif c.get("cmd") in HANDLERS:
            jobs.put(c)
    # PC 쪽 프로그램이 종료되면(stdin 닫힘) 시리얼 포트를 정리하고 끝냄
    time.sleep(0.3)
    do_disconnect(None)


_real_in = sys.stdin
main()
