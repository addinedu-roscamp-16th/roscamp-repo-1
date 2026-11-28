#!/bin/bash
# 젯코봇 동작 플레이어 실행 → 브라우저가 열림
# 처음 한 번: 우클릭 → "프로그램으로 실행"  (그 뒤로는 바탕화면 아이콘으로)
HERE="$(cd "$(dirname "$0")" && pwd)"
URL="http://127.0.0.1:8765/"
chmod +x "$HERE"/동작플레이어.sh "$HERE"/robot_link/launch/*.sh 2>/dev/null

# 바탕화면·앱 목록 아이콘 (처음 한 번)
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
APP="$HOME/.local/share/applications/jetcobot-motion-player.desktop"
if [ ! -f "$APP" ] || ! grep -q "$HERE" "$APP"; then
    mkdir -p "$(dirname "$APP")"
    cat > "$APP" <<D
[Desktop Entry]
Type=Application
Name=젯코봇 동작 플레이어
Comment=공유 동작을 RViz·실제 로봇에서 재생
Exec=bash "$HERE/동작플레이어.sh"
Icon=media-playback-start
Terminal=false
Categories=Development;
D
    if [ -d "$DESK" ]; then
        cp "$APP" "$DESK/젯코봇 동작 플레이어.desktop"
        chmod +x "$DESK/젯코봇 동작 플레이어.desktop"
        gio set "$DESK/젯코봇 동작 플레이어.desktop" metadata::trusted true 2>/dev/null
    fi
fi

# 이미 켜져 있으면 브라우저만 열기
if curl -s -o /dev/null --max-time 1 "$URL"; then
    xdg-open "$URL" >/dev/null 2>&1; exit 0
fi
cd "$HERE" && exec python3 player/server.py
