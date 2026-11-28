"""새 로봇 등록: 로봇 비밀번호로 한 번만 접속해 팀 키를 넣고, MAC·호스트 키를 robots.json 에 기록
(sshpass·paramiko 없이 OpenSSH 의 SSH_ASKPASS 로 비밀번호 전달. 비밀번호는 저장하지 않음)"""
import ipaddress
import json
import os
import re
import stat
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEAM = os.path.join(os.path.dirname(HERE), "robot_link", "team")
ROBOTS = os.path.join(TEAM, "robots.json")
KEY = os.path.join(TEAM, "id_team")
# 젯코봇 테스트 도구의 로봇 목록 — 이 PC 에 있으면 두 목록을 항상 같게 유지 (같은 팀 키를 씀)
TESTER_ROBOTS = os.path.expanduser("~/addinedu/cobot_tester/team/robots.json")


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return []


def _save(p, robots):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(robots, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def sync_lists(log=None):
    """플레이어·테스트 도구 로봇 목록 합치기 (이름 기준, 같은 이름이면 플레이어 쪽 정보 우선). 바뀐 파일만 씀"""
    paths = [ROBOTS] + ([TESTER_ROBOTS] if os.path.exists(TESTER_ROBOTS) else [])
    merged = {}
    for p in reversed(paths):                 # 테스트 도구 먼저, 플레이어가 덮어씀
        for r in _load(p):
            merged[r["alias"]] = {**merged.get(r["alias"], {}), **r}
    order = [r["alias"] for p in paths for r in _load(p)]
    robots = [merged[a] for a in dict.fromkeys(order)]
    for p in paths:
        if _load(p) != robots:
            _save(p, robots)
            if log:
                log(f"[로봇 목록] 합침 → {os.path.relpath(p, os.path.expanduser('~'))} ({len(robots)}대)")
    return robots


def _pubkey():
    r = subprocess.run(["ssh-keygen", "-y", "-f", KEY], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("팀 공용 키(robot_link/team/id_team)가 없습니다. jetcobot-team.key 를 다운로드 폴더에 두세요.")
    return r.stdout.strip() + " jetcobot-team-shared"


def register(alias, ip, user, password, log=print):
    alias, ip, user = alias.strip(), ip.strip(), (user or "jetcobot").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}", alias):
        raise ValueError("이름은 영문·숫자·_·- 로 2~40자 (예: jetcobot_ab12)")
    ipaddress.ip_address(ip)
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        raise ValueError("사용자 이름이 올바르지 않습니다.")
    if not password:
        raise ValueError("로봇 비밀번호를 넣어 주세요 (키 등록에 한 번만 쓰고 저장하지 않음).")
    robots = sync_lists()
    if any(r["alias"] == alias for r in robots):
        raise ValueError(f"'{alias}' 은 이미 등록되어 있습니다.")
    pub = _pubkey()

    log(f"[등록] {ip} 호스트 키 확인 중…")
    r = subprocess.run(["ssh-keyscan", "-T", "5", "-t", "ed25519", ip], capture_output=True, text=True)
    line = next((l for l in r.stdout.splitlines() if " ssh-ed25519 " in l), "")
    if not line:
        raise RuntimeError(f"{ip} 에 SSH 로 닿지 않습니다. 로봇 전원·Wi-Fi·IP 를 확인하세요.")
    hostkey = line.split(" ", 1)[1].strip()

    with tempfile.TemporaryDirectory() as td:
        kh = os.path.join(td, "known_hosts")
        open(kh, "w").write(f"{ip} {hostkey}\n")
        ask = os.path.join(td, "askpass.sh")
        open(ask, "w").write('#!/bin/sh\nprintf "%s\\n" "$ROBOT_PW"\n')
        os.chmod(ask, stat.S_IRWXU)
        env = dict(os.environ, SSH_ASKPASS=ask, SSH_ASKPASS_REQUIRE="force", ROBOT_PW=password, DISPLAY=os.environ.get("DISPLAY", ":0"))
        remote = (
            "set -e; umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; "
            f"grep -qF '{pub.split()[1]}' ~/.ssh/authorized_keys || echo '{pub}' >> ~/.ssh/authorized_keys; "
            "dev=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i==\"dev\") print $(i+1)}'); "
            "[ -n \"$dev\" ] || dev=$(ls /sys/class/net | grep -v lo | head -1); "
            "echo MAC=$(cat /sys/class/net/$dev/address); echo HOST=$(hostname); "
            "ls /dev/ttyJETCOBOT >/dev/null 2>&1 && echo SERIAL=ok || echo SERIAL=none")
        log(f"[등록] {user}@{ip} 에 비밀번호로 접속해 팀 키 등록 중…")
        r = subprocess.run(["ssh", "-F", "/dev/null", "-o", f"UserKnownHostsFile={kh}", "-o", "StrictHostKeyChecking=yes",
                            "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password,keyboard-interactive",
                            "-o", "NumberOfPasswordPrompts=1", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR",
                            f"{user}@{ip}", remote], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=40)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        if any("denied" in m.lower() for m in msg):
            raise RuntimeError("비밀번호가 틀렸거나 사용자 이름이 다릅니다.")
        raise RuntimeError("접속 실패: " + (msg[-1] if msg else f"코드 {r.returncode}"))
    out = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)

    log("[등록] 키로 다시 접속되는지 확인 중…")
    with tempfile.TemporaryDirectory() as td:
        kh = os.path.join(td, "known_hosts")
        open(kh, "w").write(f"{ip} {hostkey}\n")
        v = subprocess.run(["ssh", "-F", "/dev/null", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                            "-o", f"UserKnownHostsFile={kh}", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
                            "-o", "LogLevel=ERROR", f"{user}@{ip}", "echo ok"], capture_output=True, text=True, timeout=20)
    if v.stdout.strip() != "ok":
        raise RuntimeError("키는 넣었지만 키 접속이 안 됩니다: " + v.stderr.strip()[-200:])

    robots.append({"alias": alias, "ip": ip, "user": user, "hostkey": hostkey, "mac": out.get("MAC", "").lower(),
                   "hostname": out.get("HOST", "")})
    _save(ROBOTS, robots)
    sync_lists()                              # 테스트 도구 목록에도 같이
    note = "" if out.get("SERIAL") == "ok" else " (주의: 로봇에 /dev/ttyJETCOBOT 이 안 보입니다 — 팔 연결을 확인하세요)"
    log(f"[등록] ✅ {alias} 등록 완료 — MAC {out.get('MAC', '?')}, 호스트 이름 {out.get('HOST', '?')}{note}")
    return robots[-1]
