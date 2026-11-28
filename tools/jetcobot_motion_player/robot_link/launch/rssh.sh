#!/bin/bash
# 로봇 접속용 ssh. 사용: rssh.sh <별칭|user@IP> [원격 명령]
# team/robots.json 에 있는 로봇이면 팀 공용 키로 바로 접속 (팀원 설정 필요 없음),
# IP 가 바뀌어 접속이 안 되면 같은 네트워크에서 MAC 주소로 다시 찾아 접속.
HERE="$(cd "$(dirname "$0")/.." && pwd)"
T="$HERE/team"
H="$1"; shift
OPTS=(-o BatchMode=yes -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3)
info() { python3 -c "import json,sys;r=[x for x in json.load(open('$T/robots.json',encoding='utf-8')) if sys.argv[1] in [x['alias']]+x.get('old',[])];print(r[0][sys.argv[2]] if r else '')" "$H" "$1" 2>/dev/null; }
IP="$(info ip)"
A="$(info alias)"
C="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$T/ip_cache.json" "$A" 2>/dev/null)"
[ -n "$IP" ] && [ -n "$C" ] && IP="$C"          # 이 PC에서 전에 찾은 IP
if [ -z "$IP" ] || [ ! -f "$T/id_team" ]; then
    exec ssh "${OPTS[@]}" "$H" "$@"          # 팀 로봇이 아니면 평소 ssh (~/.ssh/config)
fi
chmod 600 "$T/id_team" 2>/dev/null
KH="$T/known_hosts"; echo "jetcobot-team $(info hostkey)" > "$KH"
up() { timeout 3 bash -c "</dev/tcp/$1/22" 2>/dev/null; }
mac_of() { ip neigh show "$1" 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="lladdr") print tolower($(i+1))}'; }
M="$(mac_of "$IP")"; W="$(info mac | tr A-Z a-z)"
# IP 가 열려 있어도 MAC 이 다르면 (DHCP 로 그 IP 를 다른 기기가 받음) 다시 찾기
if ! up "$IP" || { [ -n "$W" ] && M="$(mac_of "$IP")" && [ -n "$M" ] && [ "$M" != "$W" ]; }; then
    IP="$(python3 "$HERE/launch/find_robot.py" "$H")" || exit 255
fi
exec ssh -F /dev/null -i "$T/id_team" -o IdentitiesOnly=yes -o HostKeyAlias=jetcobot-team \
    -o UserKnownHostsFile="$KH" -o StrictHostKeyChecking=yes -o LogLevel=ERROR \
    "${OPTS[@]}" "$(info user)@$IP" "$@"
