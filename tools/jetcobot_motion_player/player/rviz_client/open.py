#!/usr/bin/env python3
"""팀원 컴퓨터의 'RViz 재생기' — 웹페이지의 jetcobot-rviz:// 링크를 받아 이 컴퓨터에서 RViz 재생

  jetcobot-rviz://play?rate=1&loop=0&f=<동작파일>&f=<동작파일2>
  jetcobot-rviz://stop
설치: 플레이어 페이지의 'RViz 재생기 설치' (rviz_install.sh) — 서버 주소·접속 코드는 config.json 에 저장됨
"""
import json
import os
import signal
import subprocess
import sys
import urllib.parse
import urllib.request

D = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(D, "config.json")))
PIDF = os.path.join(D, "rviz.pid")
CACHE = os.path.join(D, "cache")
ROS = "/opt/ros/jazzy/setup.bash"


def note(msg):
    subprocess.Popen(["notify-send", "-i", "applications-science", "젯코봇 RViz 재생기", msg],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_old():
    try:
        pid = int(open(PIDF).read())
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        pass


def sync_scene(name):
    """서버의 장면(맵·웍 공구 모델)이 없거나 바뀌었으면 받아 옴"""
    base = CFG["server"].rstrip("/")
    code = urllib.parse.quote(CFG["code"])
    try:
        lst = json.load(urllib.request.urlopen(f"{base}/api/scenes?code={code}", timeout=5))
    except Exception:
        return
    info = next((x for x in lst if x["name"] == name), None)
    if not info:
        return
    hf = os.path.join(D, "scenes", name, ".hash")
    if os.path.exists(hf) and open(hf).read() == info["hash"]:
        return
    note(f"장면 '{info['label'] or name}' 받는 중…")
    import io
    import shutil
    import tarfile
    data = urllib.request.urlopen(f"{base}/scenes/{urllib.parse.quote(name)}.tar.gz?code={code}", timeout=60).read()
    sd = os.path.join(D, "scenes")
    shutil.rmtree(os.path.join(sd, name), ignore_errors=True)
    os.makedirs(sd, exist_ok=True)
    tarfile.open(fileobj=io.BytesIO(data)).extractall(sd)
    open(hf, "w").write(info["hash"])


def main():
    url = urllib.parse.urlparse(sys.argv[1] if len(sys.argv) > 1 else "jetcobot-rviz://stop")
    stop_old()
    if url.netloc == "stop" or url.path.strip("/") == "stop":
        return
    q = urllib.parse.parse_qs(url.query)
    files = q.get("f", [])
    if not files:
        return note("재생할 동작이 없습니다.")
    if not os.path.exists(ROS):
        return note("ROS2 Jazzy 가 없습니다 (/opt/ros/jazzy). RViz 재생은 ROS2 가 설치된 컴퓨터에서만 됩니다.")
    os.makedirs(CACHE, exist_ok=True)
    paths = []
    for f in files:
        name = os.path.basename(f)
        src = f"{CFG['server'].rstrip('/')}/motions/{urllib.parse.quote(name)}?code={urllib.parse.quote(CFG['code'])}"
        dst = os.path.join(CACHE, name)
        try:
            urllib.request.urlretrieve(src, dst)
        except Exception as e:
            return note(f"동작 파일을 못 받았습니다 ({e}). 서버 노트북이 켜져 있는지 확인하세요.")
        paths.append(dst)
    scene = os.path.basename(q.get("scene", [""])[0])
    want = scene
    if not want:                                        # 동작 파일에 적힌 장면
        try:
            want = json.load(open(paths[0], encoding="utf-8")).get("scene", "")
        except Exception:
            want = ""
    if want and want != "robot":
        sync_scene(want)
    rate = q.get("rate", ["1"])[0]
    loop = " --loop" if q.get("loop", ["0"])[0] == "1" else ""
    quoted = " ".join("'" + p.replace("'", "'\\''") + "'" for p in paths)
    mount = q.get("mount", [""])[0]
    sc = (f" --scene '{scene}'" if scene else "") + (f" --mount {mount}" if mount in ("robot1", "robot2") else "")
    cmd = f"source {ROS} && exec python3 '{os.path.join(D, 'tools', 'play_rviz.py')}' {quoted} --rate {rate}{loop}{sc}"
    p = subprocess.Popen(["bash", "-c", cmd], start_new_session=True,
                         stdout=open(os.path.join(D, "rviz.log"), "w"), stderr=subprocess.STDOUT)
    open(PIDF, "w").write(str(p.pid))


if __name__ == "__main__":
    main()
