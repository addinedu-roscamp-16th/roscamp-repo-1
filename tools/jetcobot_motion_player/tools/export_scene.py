#!/usr/bin/env python3
"""(관리자용) 젯코봇 테스트 도구의 맵 → 공유 폴더 scenes/<맵>/ 로 내보내기 (RViz 장면)
   python3 tools/export_scene.py kitchen_table_wok_v2 [--label "주방 + 웍 공구"]

결과: scenes/<맵>/scene.urdf (메시 경로 = meshes/… 상대 경로), meshes/, scene.json
      로봇은 맵의 자리마다 robot1_…, robot2_… 접두어가 붙은 관절 이름을 가짐
"""
import argparse
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAPS = os.path.expanduser("~/addinedu/cobot_tester/maps")
sys.path.insert(0, MAPS)
import mapfile  # noqa: E402

BASE_JOINTS = ["joint2_to_joint1", "joint3_to_joint2", "joint4_to_joint3",
               "joint5_to_joint4", "joint6_to_joint5", "joint6output_to_joint6"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    root = ET.fromstring(mapfile.to_ros(a.map))
    out = os.path.join(ROOT, "scenes", a.map)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "meshes"))
    used = {}
    for m in root.iter("mesh"):
        src = m.get("filename").replace("file://", "")
        if src not in used:
            base = os.path.basename(src)
            name, n = base, 1
            while name in used.values():
                n += 1
                name = f"{os.path.splitext(base)[0]}_{n}{os.path.splitext(base)[1]}"
            shutil.copy(src, os.path.join(out, "meshes", name))
            used[src] = name
        m.set("filename", "meshes/" + used[src])
    ET.ElementTree(root).write(os.path.join(out, "scene.urdf"), encoding="unicode")
    mounts = sorted(l.get("name")[:-6] for l in root.findall("link") if l.get("name", "").endswith("_mount"))
    joints = {m: [f"{m}_{j}" for j in BASE_JOINTS] for m in mounts}
    info = {"name": a.map, "label": a.label or a.map, "fixed_frame": "world", "mounts": mounts, "joints": joints}
    json.dump(info, open(os.path.join(out, "scene.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rv = os.path.join(MAPS, a.map, a.map + ".rviz")       # 테스트 도구에서 쓰던 시점 그대로
    if os.path.isfile(rv):
        shutil.copy(rv, os.path.join(out, "scene.rviz"))
    import subprocess                                    # 법선 빠진 STL 은 RViz 에서 검게 보임 → 고쳐 넣기
    subprocess.run([sys.executable, os.path.join(HERE, "fix_stl_normals.py"), os.path.join(out, "meshes")])
    size = sum(os.path.getsize(os.path.join(out, "meshes", f)) for f in os.listdir(os.path.join(out, "meshes")))
    print(f"scenes/{a.map}: 메시 {len(used)}개 {size / 1e6:.1f}MB, 로봇 자리 {mounts}")


if __name__ == "__main__":
    main()
