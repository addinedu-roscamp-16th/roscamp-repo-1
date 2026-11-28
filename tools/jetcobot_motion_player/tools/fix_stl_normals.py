#!/usr/bin/env python3
"""바이너리 STL 의 면 법선이 0 이면 꼭짓점으로 다시 계산해 넣기 (RViz 에서 검게 보이는 문제)
   python3 tools/fix_stl_normals.py <파일.stl 또는 폴더> ...   → 고친 파일 수 출력"""
import os
import sys

import numpy as np

REC = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])


def fix(path):
    b = open(path, "rb").read()
    if len(b) < 84:
        return False
    n = int(np.frombuffer(b, "<u4", 1, 80)[0])
    if len(b) != 84 + n * 50:          # ASCII STL 등은 건너뜀
        return False
    t = np.frombuffer(b, REC, n, 84).copy()
    if np.abs(t["n"]).sum(axis=1).min() > 1e-6:
        return False                   # 이미 법선이 있음
    v = t["v"].astype(np.float64)
    nr = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    ln = np.linalg.norm(nr, axis=1, keepdims=True)
    t["n"] = np.where(ln > 0, nr / np.maximum(ln, 1e-12), 0).astype("<f4")
    with open(path, "wb") as f:
        f.write(b[:84])
        f.write(t.tobytes())
    return True


def main():
    done = 0
    for a in sys.argv[1:]:
        files = [os.path.join(r, f) for r, _, fs in os.walk(a) for f in fs] if os.path.isdir(a) else [a]
        for f in files:
            if f.lower().endswith(".stl") and fix(f):
                done += 1
    print(f"법선 고친 STL: {done}개")


if __name__ == "__main__":
    main()
