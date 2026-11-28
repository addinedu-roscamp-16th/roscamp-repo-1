#!/usr/bin/env python3
"""로봇 IP가 바뀌었을 때 같은 네트워크에서 다시 찾기 (Wi-Fi MAC 주소로 구분)
사용: python3 find_robot.py <별칭>   → 찾으면 team/ip_cache.json 에 저장하고 IP 출력"""
import ipaddress
import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "team", "robots.json")
CACHE = os.path.join(HERE, "..", "team", "ip_cache.json")   # 이 PC에서 찾은 IP (저장소에 안 올림)


def local_nets():
    out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True).stdout
    nets = []
    for line in out.splitlines():
        p = line.split()
        if p[1] == "lo":
            continue
        n = ipaddress.ip_interface(p[3]).network
        if n.prefixlen < 24:      # 너무 넓으면 /24 만
            n = ipaddress.ip_interface(f"{p[3].split('/')[0]}/24").network
        nets.append(n)
    return nets


def knock(ip):
    try:
        with socket.create_connection((str(ip), 22), timeout=0.4):
            return str(ip)
    except OSError:
        return None


def arp():
    tab = {}
    out = subprocess.run(["ip", "neigh"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        p = line.split()
        if "lladdr" in p:
            tab[p[p.index("lladdr") + 1].lower()] = p[0]
    return tab


def main():
    alias = sys.argv[1]
    robots = json.load(open(PATH, encoding="utf-8"))
    r = next(x for x in robots if alias in [x["alias"]] + x.get("old", []))
    print(f"[{r['alias']}] {r['ip']} 에 없음 → 같은 네트워크에서 찾는 중…", file=sys.stderr)
    hosts = [h for n in local_nets() for h in n.hosts()]
    with ThreadPoolExecutor(128) as ex:
        list(ex.map(knock, hosts))
    ip = arp().get(r["mac"].lower())
    if not ip or not knock(ip):
        print(f"[{r['alias']}] 찾지 못함 — 로봇 전원과 Wi-Fi(AIE_509_5G)를 확인하세요.", file=sys.stderr)
        sys.exit(1)
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    cache[r["alias"]] = ip
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=2)
    print(f"[{r['alias']}] 찾음: {ip}", file=sys.stderr)
    print(ip)


if __name__ == "__main__":
    main()
