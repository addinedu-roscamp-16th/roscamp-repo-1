#!/usr/bin/env bash
# FryBot DB 접속 (비밀번호는 .env에서 읽음 → 직접 입력·오타 없음)
# 사용: ./db/connect.sh [계정] [호스트] [-e "SQL"]
#   ./db/connect.sh                         # frybot@127.0.0.1 대화형
#   ./db/connect.sh team_ro 192.168.0.8     # 팀 서버에 조회 계정으로
#   ./db/connect.sh frybot 127.0.0.1 -e "SELECT * FROM v_robot_board"
set -e
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env가 없습니다. cp .env.example .env 후 비밀번호를 넣으세요." >&2; exit 1; }
set -a; . ./.env; set +a
USER_NAME="${1:-frybot}"; HOST="${2:-127.0.0.1}"; shift $(( $# > 2 ? 2 : $# )) || true
case "$USER_NAME" in
  frybot)   PW="$MYSQL_PASSWORD" ;;
  team_dev) PW="$TEAM_DEV_PASSWORD" ;;
  team_ro)  PW="$TEAM_RO_PASSWORD" ;;
  root)     PW="$MYSQL_ROOT_PASSWORD" ;;
  *) echo "계정은 frybot / team_dev / team_ro / root 중 하나" >&2; exit 1 ;;
esac
MYSQL_PWD="$PW" exec mysql -h "$HOST" -P 3306 -u "$USER_NAME" --default-character-set=utf8mb4 -t frybot "$@"
