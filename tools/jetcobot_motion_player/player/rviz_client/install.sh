#!/bin/bash
# 젯코봇 RViz 재생기 설치 (팀원 컴퓨터에서 처음 한 번)
# 설치 후: 플레이어 웹페이지의 '▶ RViz (내 컴퓨터)' 버튼 → 이 컴퓨터에 RViz 창이 뜸
SERVER="__SERVER__"
CODE="__CODE__"
D="$HOME/.local/share/jetcobot-rviz"
say() { echo "$1"; command -v notify-send >/dev/null && notify-send -i applications-science "젯코봇 RViz 재생기" "$1"; }

mkdir -p "$D"
if ! curl -fsS "$SERVER/rviz_bundle.tar.gz?code=$CODE" | tar xz -C "$D"; then
    say "설치 실패: 서버($SERVER)에서 파일을 못 받았습니다. 같은 와이파이인지, 서버 노트북이 켜져 있는지 확인하세요."
    exit 1
fi
printf '{"server": "%s", "code": "%s"}\n' "$SERVER" "$CODE" > "$D/config.json"

APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
cat > "$APPS/jetcobot-rviz.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=젯코봇 RViz 재생기
Exec=python3 "$D/open.py" %u
Icon=applications-science
NoDisplay=true
Terminal=false
MimeType=x-scheme-handler/jetcobot-rviz;
EOF
update-desktop-database "$APPS" 2>/dev/null
xdg-mime default jetcobot-rviz.desktop x-scheme-handler/jetcobot-rviz

if [ -f /opt/ros/jazzy/setup.bash ]; then
    say "설치 완료. 플레이어 페이지를 새로고침하고 '▶ RViz (내 컴퓨터)' 를 누르세요. 처음엔 브라우저가 '열기'를 물어봅니다."
else
    say "설치는 됐지만 이 컴퓨터에 ROS2 Jazzy 가 없어 RViz 재생은 안 됩니다."
fi
