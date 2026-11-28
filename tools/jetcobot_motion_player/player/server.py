#!/usr/bin/env python3
"""젯코봇 동작 플레이어 — 브라우저 화면 + 이 PC 에서 RViz·실제 로봇 재생

  ./동작플레이어.sh  (또는 python3 player/server.py)  → http://127.0.0.1:8765

- 동작 목록: motions/*.json (tools/motion_lib.py 형식)
- RViz: tools/play_rviz.py 를 띄움 (ROS2 Jazzy)
- 실제 로봇: SSH 로 로봇에 robot_link/agent.py 를 보내 실행 (로봇에 설치할 것 없음)
  접속은 robot_link/launch/rssh.sh — 팀 로봇(robot_link/team/robots.json)이면 팀 공용 키 + IP 자동 찾기
"""
import base64
import glob
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import motion_lib as ml  # noqa: E402

LINK = os.path.join(ROOT, "robot_link")
TEAM = os.path.join(LINK, "team")
RSSH = os.path.join(LINK, "launch", "rssh.sh")
PORT = int(os.environ.get("PLAYER_PORT", "8765"))
CODE_FILE = os.path.join(HERE, "access_code.txt")     # 팀 접속 코드 (저장소에 안 올림). 지우면 새로 만듦
LOCAL = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def access_code():
    if not os.path.exists(CODE_FILE):
        import random
        code = "wok" + "".join(random.choice("23456789") for _ in range(4))
        with open(CODE_FILE, "w") as f:
            f.write(code + "\n")
    return open(CODE_FILE).read().strip()


def lan_urls():
    out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True).stdout
    urls = []
    for line in out.splitlines():
        p = line.split()
        if p[1] != "lo" and not p[1].startswith("docker"):
            urls.append({"dev": p[1], "url": f"http://{p[3].split('/')[0]}:{PORT}/"})
    return urls


LOGIN_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>젯코봇 동작 플레이어</title><style>body{font:15px system-ui,sans-serif;display:grid;place-items:center;height:90vh;margin:0}
form{display:flex;gap:8px;flex-direction:column;width:260px}input,button{font:inherit;padding:8px;border-radius:7px;border:1px solid #bbb}
button{background:#2f6fed;color:#fff;border:0}p{color:#c00;margin:0}</style></head><body><form action="/login">
<b>젯코봇 동작 플레이어</b><span>팀 접속 코드</span><input name="code" autofocus>%s<button>들어가기</button></form></body></html>"""
REMOTE_PY = ('P=~/venv/mycobot/bin/python; [ -x "$P" ] || P=~/venv/jetcobot/bin/python; '
             '[ -x "$P" ] || P=python3; "$P"')

LOG = []                 # [(번호, 종류, 글)]
LOG_LOCK = threading.Lock()


def log(text, kind="info"):
    with LOG_LOCK:
        LOG.append((len(LOG), kind, text.rstrip("\n")))
        if len(LOG) > 600:
            del LOG[:-500]


def find_team_key():
    """팀 공용 키가 없으면 jetcobot-team.key 를 찾아 꺼냄 (다운로드·바탕화면·이 폴더)"""
    if os.path.exists(os.path.join(TEAM, "id_team")):
        return True
    home = os.path.expanduser("~")
    for d in [ROOT, os.path.dirname(ROOT)] + [os.path.join(home, x) for x in
                                              ("Downloads", "다운로드", "Desktop", "바탕화면", "")]:
        k = os.path.join(d, "jetcobot-team.key")
        if os.path.isfile(k):
            txt = open(k).read()
            i = txt.find("-----BEGIN OPENSSH PRIVATE KEY-----")
            j = txt.find("-----END OPENSSH PRIVATE KEY-----", i)
            if i >= 0 and j > 0:
                p = os.path.join(TEAM, "id_team")
                with open(p, "w") as f:
                    f.write(txt[i:j + len("-----END OPENSSH PRIVATE KEY-----")] + "\n")
                os.chmod(p, 0o600)
                log(f"팀 공용 키를 찾았습니다: {k}")
                return True
    return False


# ───────────────────────── 실제 로봇 (SSH agent) ─────────────────────────
class Robot:
    def __init__(self):
        self.proc, self.host, self.ready, self.connected = None, "", False, False
        self.busy, self.angles, self.rec_name, self.rec_meta = "", None, None, {}
        self.coords, self.state_t, self.grip = None, 0.0, None
        self.lock = threading.Lock()

    def start(self, host):
        if self.proc and self.proc.poll() is None:
            return "이미 연결되어 있습니다."
        find_team_key()
        b64 = base64.b64encode(open(os.path.join(LINK, "agent.py"), "rb").read()).decode()
        remote = f"{REMOTE_PY} -u -c \"import base64;exec(base64.b64decode('{b64}').decode('utf-8'))\""
        self.host, self.ready, self.connected, self.busy = host, False, False, "접속 중"
        log(f"→ {host} 에 SSH 접속 중…", "send")
        self.proc = subprocess.Popen(["bash", RSSH, host, remote], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._err, args=(self.proc,), daemon=True).start()
        return None

    def send(self, **c):
        if not (self.proc and self.proc.poll() is None):
            raise RuntimeError("로봇이 연결되어 있지 않습니다.")
        with self.lock:
            self.proc.stdin.write(json.dumps(c, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()

    def stop_link(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.send(cmd="stop")
                self.proc.stdin.close()
            except Exception:
                pass
            threading.Timer(1.5, lambda p=self.proc: p.poll() is None and p.kill()).start()

    def _err(self, p):
        for line in p.stderr:
            if line.strip():
                log(line, "info" if line.startswith("[") else "err")   # rssh.sh 의 '[로봇] 찾는 중…' 안내는 오류 아님

    def _read(self, p):
        buf = {"out": "", "err": ""}
        for line in p.stdout:
            try:
                m = json.loads(line)
            except ValueError:
                log(line, "out")
                continue
            t = m.get("type")
            if t == "ready":
                self.ready = True
                log("로봇 쪽 프로그램 시작 → 로봇 연결", "ok")
                self.send(cmd="connect")
            elif t in ("out", "err"):                 # print() 가 조각으로 오므로 줄 단위로 모아서
                buf[t] += m["text"]
                *lines, buf[t] = buf[t].split("\n")
                for ln in lines:
                    if not ln.strip():
                        continue
                    log(ln, t)
                    if ln.startswith("그리퍼 값:"):
                        try:
                            self.grip = int(ln.split(":")[1].strip())
                        except ValueError:
                            pass
            elif t == "state":
                self.angles, self.coords, self.state_t = m.get("angles"), m.get("coords"), time.time()
            elif t == "done":
                if m["cmd"] == "connect":
                    self.connected = bool(m["ok"])
                    log("● 로봇 연결됨" if m["ok"] else "로봇 연결 실패", "ok" if m["ok"] else "err")
                if not m["ok"] and m.get("error"):
                    log(m["error"], "err")
                self.busy = ""
            elif t == "traj":                       # 손으로 따기 결과
                pts = m.get("points", [])
                if len(pts) >= 2 and self.rec_name:
                    try:
                        ml.save(self.rec_name, pts, robot=self.rec_meta.get("robot", self.host),
                                made_by="손으로 따기 (동작 플레이어)", status="시험",
                                author=self.rec_meta.get("author", ""), notes=self.rec_meta.get("notes", ""),
                                play_hint={"speed": 50, "lead": 0.12, "hz": 30})
                        log(f"저장했습니다: {self.rec_name} ({len(pts)}점)", "ok")
                    except Exception as e:
                        log(f"저장 실패: {e}", "err")
                else:
                    log("녹화된 점이 너무 적어 저장하지 않았습니다.", "err")
                self.rec_name = None
        code = p.wait()
        if p is self.proc:
            self.ready = self.connected = False
            self.busy = ""
            log(f"SSH 연결 끝 (코드 {code})" + (" — 로봇 전원·Wi-Fi·키 파일을 확인하세요" if code == 255 else ""),
                "info" if code == 0 else "err")


ROBOT = Robot()


# ───────────────────────── RViz ─────────────────────────
class Rviz:
    def __init__(self):
        self.proc = None

    def play(self, files, rate, loop, scene="", mount=""):
        self.stop()
        paths = " ".join("'" + f.replace("'", "'\\''") + "'" for f in files)
        cmd = (f"source /opt/ros/jazzy/setup.bash && exec python3 -u '{os.path.join(ROOT, 'tools', 'play_rviz.py')}' "
               f"{paths} --rate {rate}" + (" --loop" if loop else "") + (f" --scene '{scene}'" if scene else "") + (f" --mount '{mount}'" if mount else ""))
        self.proc = subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, start_new_session=True)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, p):
        for line in p.stdout:
            if line.startswith("▶") or line.startswith("■") or "rror" in line:
                log("[RViz] " + line, "out")
        p.wait()

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.running():
            try:
                os.killpg(self.proc.pid, 15)
            except Exception:
                pass


RVIZ = Rviz()


# ───────────────────────── HTTP ─────────────────────────
def motions():
    out = []
    for i, p in enumerate(ml._files(), 1):
        m, pts = ml.load(p)
        step = max(1, len(pts) // 300)
        out.append({"no": i, "file": os.path.basename(p), "name": m["name"], "status": m.get("status", ""),
                    "robot": m.get("robot", ""), "made_by": m.get("made_by", ""), "author": m.get("author", ""),
                    "created": m.get("created", ""), "notes": m.get("notes", ""), "hint": m.get("play_hint", {}),
                    "dur": pts[-1][0], "n": len(pts), "scene": m.get("scene", ""), "mount": m.get("mount", ""), "points": pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])})
    return out


def scenes():
    """scenes/<이름>/scene.json 목록 + 내용 해시 (팀원 RViz 재생기가 바뀐 장면만 새로 받게)"""
    import hashlib
    out = []
    for d in sorted(glob.glob(os.path.join(ROOT, "scenes", "*", "scene.json"))):
        sd = os.path.dirname(d)
        h = hashlib.md5()
        for root, _, fs in os.walk(sd):
            for f in sorted(fs):
                st = os.stat(os.path.join(root, f))
                h.update(f"{f}{st.st_size}{int(st.st_mtime)}".encode())
        info = json.load(open(d, encoding="utf-8"))
        out.append({"name": os.path.basename(sd), "label": info.get("label", ""), "hash": h.hexdigest()})
    return out


ANGLE_MIN = [-168, -135, -150, -145, -165, -180]
ANGLE_MAX = [168, 135, 150, 145, 165, 180]
COORD_MIN = [-350, -350, -100, -180, -180, -180]
COORD_MAX = [350, 350, 550, 180, 180, 180]
FRONT_FILE = os.path.join(LINK, "team", "front_pose.json")    # 로봇별 '정면 대기' 자세 (그리퍼가 정면을 보게 J6 만 돌림)
FRONT_DEFAULT = {"jetcobot_aa1f": [0, 0, 0, 0, 0, 50], "jetcobot_aab4": [0, 0, 0, 0, 0, 45]}
POSES_FILE = os.path.join(ROOT, "poses.json")                 # 팀 공용 '자세 기록'


def _jload(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def _jsave(p, obj):
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def front_pose(host):
    d = {**FRONT_DEFAULT, **_jload(FRONT_FILE, {})}
    return d.get(host, [0, 0, 0, 0, 0, 0])


def nums(v, lo, hi, what):
    if not (isinstance(v, list) and len(v) == 6):
        raise ValueError(f"{what} 값 6개가 필요합니다.")
    out = [round(float(x), 2) for x in v]
    for i, (x, a, b) in enumerate(zip(out, lo, hi), 1):
        if not a <= x <= b:
            raise ValueError(f"{what} {i}번째 값 {x} 는 허용 범위({a}~{b}) 밖입니다.")
    return out


def robots():
    try:
        from register_robot import sync_lists
        sync_lists()
    except Exception:
        pass
    try:
        rs = json.load(open(os.path.join(TEAM, "robots.json"), encoding="utf-8"))
        return [{"alias": r["alias"], "ip": r.get("ip", "")} for r in rs]
    except Exception:
        return []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def who(self):
        ip = self.client_address[0]
        return "" if ip in LOCAL else f"[{ip.replace('::ffff:', '')}] "

    def authed(self):
        if self.client_address[0] in LOCAL:
            return True
        ck = self.headers.get("Cookie", "")
        if f"player_code={access_code()}" in [x.strip() for x in ck.split(";")]:
            return True
        from urllib.parse import parse_qs, urlparse      # RViz 재생기·설치 스크립트는 ?code= 로
        return parse_qs(urlparse(self.path).query).get("code", [""])[0] == access_code()

    def _send(self, body, ctype, code=200, extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        from urllib.parse import parse_qs, unquote, urlparse
        u = urlparse(self.path)
        if u.path == "/login":
            code = parse_qs(u.query).get("code", [""])[0].strip()
            if code == access_code():
                log(f"{self.who()}팀원 접속", "ok")
                return self._send(b"", "text/plain", 303, [("Location", "/"), (
                    "Set-Cookie", f"player_code={code}; Path=/; Max-Age=31536000; SameSite=Lax")])
            msg = "<p>코드가 틀렸습니다</p>" if code else ""
            return self._send((LOGIN_HTML % msg).encode(), "text/html; charset=utf-8")
        if not self.authed():
            if u.path in ("/", "/index.html"):
                return self._send((LOGIN_HTML % "").encode(), "text/html; charset=utf-8")
            return self._json({"ok": False, "error": "팀 접속 코드가 필요합니다. 페이지를 새로고침하세요."}, 401)
        if u.path.startswith(("/vendor/", "/model/", "/viewer3d.js")):   # 브라우저 3D 뷰어용 파일
            from urllib.parse import unquote
            rel = unquote(u.path)
            if rel == "/viewer3d.js":
                base, sub = HERE, "viewer3d.js"
            elif rel.startswith("/vendor/"):
                base, sub = os.path.join(HERE, "vendor"), rel[len("/vendor/"):]
            elif rel.startswith("/model/robot/"):
                base, sub = os.path.join(ROOT, "robot"), rel[len("/model/robot/"):]
            elif rel.startswith("/model/scenes/"):
                base, sub = os.path.join(ROOT, "scenes"), rel[len("/model/scenes/"):]
            else:
                return self.send_error(404)
            f = os.path.realpath(os.path.join(base, sub))
            if not f.startswith(os.path.realpath(base) + os.sep) or not os.path.isfile(f):
                return self.send_error(404)
            ct = {".js": "text/javascript; charset=utf-8", ".urdf": "application/xml", ".json": "application/json",
                  ".stl": "application/octet-stream"}.get(os.path.splitext(f)[1].lower(), "application/octet-stream")
            return self._send(open(f, "rb").read(), ct, 200, [("Cache-Control", "max-age=3600")])
        if u.path == "/rviz_install.sh":                     # 팀원 컴퓨터용 RViz 재생기 설치 스크립트
            host = self.headers.get("Host", f"127.0.0.1:{PORT}")
            sh = open(os.path.join(HERE, "rviz_client", "install.sh"), encoding="utf-8").read()
            sh = sh.replace("__SERVER__", f"http://{host}").replace("__CODE__", access_code())
            log(f"{self.who()}RViz 재생기 설치 파일 받음", "info")
            return self._send(sh.encode(), "text/x-shellscript; charset=utf-8", 200,
                              [("Content-Disposition", "attachment; filename=rviz_install.sh")])
        if u.path == "/rviz_bundle.tar.gz":                  # 설치 스크립트가 받아 가는 파일 묶음
            import io
            import tarfile
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as t:
                t.add(os.path.join(ROOT, "tools", "play_rviz.py"), "tools/play_rviz.py")
                t.add(os.path.join(ROOT, "robot"), "robot")
                t.add(os.path.join(HERE, "rviz_client", "open.py"), "open.py")
            return self._send(buf.getvalue(), "application/gzip")
        if u.path.startswith("/motions/"):                   # 동작 파일 내려받기
            p = os.path.join(ml.MOTION_DIR, os.path.basename(unquote(u.path)))
            if not os.path.isfile(p):
                return self.send_error(404)
            from urllib.parse import quote
            return self._send(open(p, "rb").read(), "application/json; charset=utf-8", 200, [(
                "Content-Disposition", f"attachment; filename*=UTF-8''{quote(os.path.basename(p))}")])
        if u.path in ("/", "/index.html"):
            b = open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif u.path == "/api/scenes":
            self._json(scenes())
        elif u.path.startswith("/scenes/") and u.path.endswith(".tar.gz"):     # 장면 묶음 (팀원 RViz 재생기용)
            import io
            import tarfile
            name = os.path.basename(u.path)[:-7]
            sd = os.path.join(ROOT, "scenes", name)
            if not os.path.isdir(sd):
                return self.send_error(404)
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as t:
                t.add(sd, name)
            return self._send(buf.getvalue(), "application/gzip")
        elif u.path == "/api/poses":
            self._json(_jload(POSES_FILE, []))
        elif self.path == "/api/motions":
            self._json(motions())
        elif self.path.startswith("/api/status"):
            since = int(self.path.split("since=")[-1]) if "since=" in self.path else 0
            with LOG_LOCK:
                lg = [x for x in LOG if x[0] >= since]
            self._json({"robot": {"host": ROBOT.host, "link": bool(ROBOT.proc and ROBOT.proc.poll() is None),
                                  "connected": ROBOT.connected, "busy": ROBOT.busy, "angles": ROBOT.angles,
                                  "recording": ROBOT.rec_name is not None, "coords": ROBOT.coords,
                                  "state_t": ROBOT.state_t, "grip": ROBOT.grip,
                                  "front": front_pose(ROBOT.host) if ROBOT.host else None},
                        "rviz": RVIZ.running(), "log": lg, "robots": robots(),
                        "local": self.client_address[0] in LOCAL, "scenes": scenes(), "urls": lan_urls(),
                        "code": access_code() if self.client_address[0] in LOCAL else "",
                        "key": os.path.exists(os.path.join(TEAM, "id_team"))})
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.authed():
            return self._json({"ok": False, "error": "팀 접속 코드가 필요합니다. 페이지를 새로고침하세요."}, 401)
        n = int(self.headers.get("Content-Length", 0))
        c = json.loads(self.rfile.read(n) or b"{}")
        try:
            r = self.api(self.path, c)
            self._json({"ok": True, **(r or {})})
        except Exception as e:
            log(str(e), "err")
            self._json({"ok": False, "error": str(e)}, 400)

    def api(self, path, c):
        who = self.who()
        def mfile(f):
            p = os.path.join(ml.MOTION_DIR, os.path.basename(f))
            if not os.path.isfile(p):
                raise ValueError("동작 파일이 없습니다: " + f)
            return p

        if path == "/api/rviz/play":
            files = [mfile(f) for f in c["files"]]
            scene = os.path.basename(c.get("scene", "") or "")
            mount = c.get("mount", "") if c.get("mount", "") in ("robot1", "robot2") else ""
            RVIZ.play(files, float(c.get("rate", 1.0)), bool(c.get("loop")), scene, mount)
            log(who + "RViz 재생: " + ", ".join(os.path.basename(f) for f in files), "send")
        elif path == "/api/rviz/note":                     # 팀원 컴퓨터에서 RViz 재생 (기록만)
            log(who + "RViz(내 컴퓨터) 재생: " + ", ".join(c.get("files", [])), "send")
        elif path == "/api/rviz/stop":
            RVIZ.stop()
            log(who + "RViz 닫음")
        elif path == "/api/robot/connect":
            log(f"{who}연결 요청", "send")
            err = ROBOT.start(c.get("host") or "jetcobot_aab4")
            if err:
                raise RuntimeError(err)
        elif path == "/api/robot/register":              # 새 로봇 등록 (비밀번호는 키 넣을 때 한 번만, 저장 안 함)
            from register_robot import register
            log(f"{who}로봇 등록 요청: {c.get('alias', '')} ({c.get('ip', '')})", "send")
            r = register(c.get("alias", ""), c.get("ip", ""), c.get("user", "jetcobot"), c.get("password", ""),
                         log=lambda t: log(t, "ok" if "✅" in t else "info"))
            return {"robot": {"alias": r["alias"], "ip": r["ip"]}}
        elif path == "/api/robot/cmd":                   # 조작 탭: 기본 조작 명령
            if not ROBOT.connected:
                raise RuntimeError("먼저 로봇을 연결하세요.")
            cmd, speed = c.get("cmd"), max(1, min(100, int(c.get("speed", 20))))
            if cmd == "home":
                ROBOT.send(cmd="home", speed=speed); what = "기본자세 [0,0,0,0,0,0]"
            elif cmd == "front":
                v = front_pose(ROBOT.host)
                ROBOT.send(cmd="angles", values=v, speed=speed); what = f"정면 대기 {v}"
            elif cmd == "angles":
                v = nums(c.get("values"), ANGLE_MIN, ANGLE_MAX, "관절 각도")
                ROBOT.send(cmd="angles", values=v, speed=speed); what = f"각도로 이동 {v}"
            elif cmd == "coords":
                v = nums(c.get("values"), COORD_MIN, COORD_MAX, "좌표")
                ROBOT.send(cmd="coords", values=v, speed=speed); what = f"좌표로 이동 {v}"
            elif cmd == "gripper":
                g = max(0, min(100, int(c.get("value", 100))))
                ROBOT.send(cmd="gripper", value=g, speed=speed); what = f"그리퍼 {g} (0=닫힘, 100=열림)"
            elif cmd in ("focus", "release", "state"):
                ROBOT.send(cmd=cmd); what = {"focus": "서보 고정", "release": "서보 풀기 (손으로 움직이기)", "state": "현재 상태 읽기"}[cmd]
            else:
                raise ValueError("모르는 조작: " + str(cmd))
            if cmd != "state":
                log(f"{who}{what}" + (f" · 속도 {speed}" if cmd in ("home", "front", "angles", "coords", "gripper") else ""), "send")
        elif path == "/api/robot/front_save":            # 지금 각도 칸 값을 이 로봇의 정면 대기로
            if not ROBOT.host:
                raise RuntimeError("먼저 로봇을 연결하세요.")
            v = nums(c.get("values"), ANGLE_MIN, ANGLE_MAX, "관절 각도")
            d = _jload(FRONT_FILE, {})
            d[ROBOT.host] = v
            _jsave(FRONT_FILE, d)
            log(f"{who}정면 대기 저장 ({ROBOT.host}): {v}", "ok")
        elif path == "/api/pose/save":
            name = (c.get("name") or "").strip()
            if not name:
                raise ValueError("자세 이름을 적어 주세요.")
            v = nums(c.get("values"), ANGLE_MIN, ANGLE_MAX, "관절 각도")
            ps = [p for p in _jload(POSES_FILE, []) if p["name"] != name]
            ps.append({"name": name, "angles": v, "robot": ROBOT.host, "by": who.strip("[] ") or "서버 노트북",
                       "created": time.strftime("%Y-%m-%d %H:%M")})
            _jsave(POSES_FILE, ps)
            log(f"{who}자세 저장: {name} {v}", "ok")
        elif path == "/api/motion/from_poses":          # 자세 기록 여러 개 → 부드럽게 이은 동작 파일
            name = (c.get("name") or "").strip()
            if not name:
                raise ValueError("동작 이름을 적어 주세요.")
            if os.path.exists(os.path.join(ml.MOTION_DIR, ml.slug(name) + ".json")):
                raise ValueError("같은 이름의 동작이 있습니다.")
            allp = {p["name"]: p for p in _jload(POSES_FILE, [])}
            seq = [allp[n] for n in c.get("poses", []) if n in allp]
            if len(seq) < 2:
                raise ValueError("자세를 2개 이상 골라 주세요.")
            seg = max(0.3, min(30.0, float(c.get("seg", 2.0))))
            hold = max(0.0, min(10.0, float(c.get("hold", 0.5))))
            dt, t, pts = 0.05, 0.0, []
            pts.append([0.0] + seq[0]["angles"])
            for a0, a1 in zip(seq, seq[1:]):
                if hold:
                    t += hold
                    pts.append([round(t, 3)] + a0["angles"])
                n = max(2, int(round(seg / dt)))
                for k in range(1, n + 1):                 # 처음·끝이 부드러운 (코사인) 보간
                    f = 0.5 - 0.5 * __import__("math").cos(__import__("math").pi * k / n)
                    pts.append([round(t + seg * k / n, 3)] + [round(x + (y - x) * f, 2) for x, y in zip(a0["angles"], a1["angles"])])
                t += seg
            if hold:
                pts.append([round(t + hold, 3)] + seq[-1]["angles"])
            host = seq[0].get("robot", "") or ROBOT.host
            where = {"jetcobot_aab4": ("kitchen_table_wok_v2", "robot2"), "jetcobot_aa1f": ("kitchen_table_wok_v2", "robot1")}.get(host)
            extra = {"scene": where[0], "mount": where[1]} if where else {}
            ml.save(name, pts, robot=host, made_by="자세 이어 만들기: " + " → ".join(p["name"] for p in seq),
                    status="시험", author=who.strip("[] ") or "서버 노트북",
                    notes=f"자세 사이 {seg}초, 머무름 {hold}초", play_hint={"speed": 50, "lead": 0.12, "hz": 30}, extra=extra)
            log(f"{who}저장했습니다: {name} (자세 {len(seq)}개 → 동작 {pts[-1][0]:.1f}초)", "ok")
        elif path == "/api/pose/delete":
            ps = _jload(POSES_FILE, [])
            _jsave(POSES_FILE, [p for p in ps if p["name"] != c.get("name")])
            log(f"{who}자세 지움: {c.get('name')}", "ok")
        elif path == "/api/robot/disconnect":
            ROBOT.stop_link()
            log(who + "연결 끊는 중…")
        elif path == "/api/robot/stop":
            ROBOT.send(cmd="stop")
            log(who + "■ 정지", "send")
        elif path == "/api/robot/play":
            if not ROBOT.connected:
                raise RuntimeError("먼저 로봇을 연결하세요.")
            items = c["files"]
            pts_all = []
            for f in items:                                     # 여러 동작은 시간을 이어 붙여 한 번에
                m, pts = ml.load(mfile(f))
                ml._check_limits(pts)
                off = pts_all[-1][0] + 1.0 if pts_all else 0.0
                if pts_all:
                    pts_all.append([off - 0.5] + pts_all[-1][1:])   # 0.5초 머무름 후 다음 동작 첫 자세로 1초
                pts_all += [[round(p[0] + off + (0.5 if off else 0), 4)] + p[1:] for p in pts]
                hint = m.get("play_hint", {})
            speed = int(c.get("speed") or hint.get("speed", 80))
            ROBOT.busy = "재생 중"
            ROBOT.send(cmd="play_traj", points=pts_all, speed=speed, mode="lead", lead=float(hint.get("lead", 0.12)),
                       hz=30, rate=float(c.get("rate", 1.0)), repeat=1)
            log(f"{who}▶ 실제 로봇 재생: {', '.join(items)} (속도 {speed}, ×{c.get('rate', 1.0)})", "send")
        elif path == "/api/robot/record_start":
            if not ROBOT.connected:
                raise RuntimeError("먼저 로봇을 연결하세요.")
            name = (c.get("name") or "").strip()
            if not name:
                raise ValueError("동작 이름을 적어 주세요.")
            if os.path.exists(os.path.join(ml.MOTION_DIR, ml.slug(name) + ".json")):
                raise ValueError("같은 이름의 동작이 있습니다.")
            ROBOT.rec_name, ROBOT.rec_meta = name, {"author": c.get("author", ""), "notes": c.get("notes", ""),
                                                   "robot": ROBOT.host}
            ROBOT.busy = "녹화 중"
            ROBOT.send(cmd="record", interval=0.1, release=True)
            log(f"{who}● 손으로 따기 시작: {name} — 3초 뒤부터 기록, 끝나면 '녹화 끝'", "send")
        elif path == "/api/robot/record_stop":
            ROBOT.send(cmd="record_stop")
            ROBOT.send(cmd="focus")                      # 녹화 끝나면 서보 다시 잠금 (팔이 처지지 않게)
            log(who + "■ 녹화 끝 → 서보 잠금", "send")
        elif path == "/api/robot/focus":
            ROBOT.send(cmd="focus")
        elif path == "/api/motion/upload":                 # 팀원이 만든 동작 파일 올리기
            m = json.loads(c["content"])
            if not (isinstance(m.get("points"), list) and len(m["points"]) >= 2 and len(m.get("joint_names", [])) == 6):
                raise ValueError("동작 파일 형식이 아닙니다 (joint_names 6개 + points 필요)")
            m.setdefault("name", os.path.splitext(os.path.basename(c.get("filename", "올린 동작")))[0])
            m.setdefault("status", "시험")
            dst = os.path.join(ml.MOTION_DIR, ml.slug(m["name"]) + ".json")
            if os.path.exists(dst) and not c.get("overwrite"):
                raise ValueError(f"같은 이름의 동작이 있습니다: {m['name']}")
            json.dump(m, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            from make_index import make_index
            make_index(quiet=True)
            log(f"{who}저장했습니다: {m['name']} (올린 파일)", "ok")
        elif path == "/api/motion/delete":                 # 지우기 = 휴지통 폴더로 옮김 (되살릴 수 있게)
            import shutil
            src = mfile(c["file"])
            name = json.load(open(src, encoding="utf-8")).get("name", c["file"])
            trash = os.path.join(ROOT, "motions_trash")
            os.makedirs(trash, exist_ok=True)
            shutil.move(src, os.path.join(trash, time.strftime("%Y%m%d_%H%M%S_") + os.path.basename(src)))
            g = os.path.join(ROOT, "graphs", os.path.splitext(os.path.basename(src))[0] + ".png")
            if os.path.exists(g):
                os.remove(g)
            from make_index import make_index
            make_index(quiet=True)
            log(f"{who}지움 (휴지통으로): {name}", "ok")
        elif path == "/api/motion/update":                 # 상태·메모 고치기
            p = mfile(c["file"])
            m = json.load(open(p, encoding="utf-8"))
            for k in ("status", "notes"):
                if k in c:
                    m[k] = c[k]
            json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            from make_index import make_index
            make_index(quiet=True)
            log(f"{who}고침: {m['name']} → 상태 {m.get('status')}", "ok")
        else:
            raise ValueError("모르는 요청: " + path)


def main():
    find_team_key()
    try:
        from register_robot import sync_lists
        sync_lists(log=log)                   # 테스트 도구에서 추가한 로봇도 메뉴에
    except Exception as e:
        log(f"로봇 목록 합치기 실패: {e}", "err")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    url = f"http://127.0.0.1:{PORT}/"
    print("동작 플레이어:", url, flush=True)
    for x in lan_urls():
        print(f"  팀원 노트북에서: {x['url']}  ({x['dev']})  접속 코드: {access_code()}", flush=True)
    log("동작 플레이어 시작")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, lambda: subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                                                      stderr=subprocess.DEVNULL)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        RVIZ.stop()
        ROBOT.stop_link()


if __name__ == "__main__":
    main()
