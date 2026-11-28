#!/usr/bin/env python3
"""(관리자용) 젯코봇 테스트 도구의 demos.json 에서 동작을 골라 motions/ 로 내보내기
   python3 tools/export_from_tester.py "동작 이름" [--status 확정] [--made-by "..."] [--name "새 이름"]
   python3 tools/export_from_tester.py --list aab4      # 이름에 aab4 가 들어간 동작 보기"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion_lib as ml  # noqa: E402

DEMOS = os.path.expanduser("~/addinedu/cobot_tester/demos.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("demo", nargs="?")
    ap.add_argument("--list")
    ap.add_argument("--name")
    ap.add_argument("--status", default="시험")
    ap.add_argument("--made-by", default="젯코봇 테스트 도구")
    ap.add_argument("--notes", default="")
    ap.add_argument("--speed", type=int, default=80)
    ap.add_argument("--lead", type=float, default=0.12)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    demos = json.load(open(DEMOS, encoding="utf-8"))
    if a.list is not None:
        for d in demos:
            if a.list in d["name"]:
                print(d["name"])
        return
    d = next((x for x in demos if x["name"] == a.demo), None)
    if d is None:
        sys.exit(f"'{a.demo}' 이 demos.json 에 없습니다 (--list 로 확인)")
    robot = d.get("robot", "")
    if d.get("slot"):
        robot = f"로봇{d['slot']} ({robot})"
    ml.save(a.name or d["name"], d["points"], robot=robot, made_by=a.made_by, status=a.status,
            author="관리자 (테스트 도구)", notes=a.notes, play_hint={"speed": a.speed, "lead": a.lead, "hz": 30},
            extra={"real": bool(d.get("real"))}, overwrite=a.overwrite)


if __name__ == "__main__":
    main()
