#!/bin/bash
# 팀 공용 계정 생성 (비밀번호는 .env에서 받음, git에 남기지 않음)
# - frybot     : 스키마 담당(ALL)  ← docker 이미지가 MYSQL_USER로 생성
# - team_dev   : 개발용 읽기/쓰기(DML), 테이블 구조 변경 불가
# - team_ro    : 조회 전용 (관제 확인, GUI 도구, 분석)
set -e
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER IF NOT EXISTS 'team_dev'@'%' IDENTIFIED BY '${TEAM_DEV_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE, SHOW VIEW ON frybot.* TO 'team_dev'@'%';
CREATE USER IF NOT EXISTS 'team_ro'@'%' IDENTIFIED BY '${TEAM_RO_PASSWORD}';
GRANT SELECT, SHOW VIEW ON frybot.* TO 'team_ro'@'%';
FLUSH PRIVILEGES;
SQL
