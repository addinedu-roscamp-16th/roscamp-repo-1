#!/usr/bin/env python3
"""motions/*.json → MOTIONS.md 목록 페이지 + graphs/<동작>.png 관절 그래프
   python3 tools/make_index.py      (save()/record() 하면 자동으로 실행됨)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion_lib as ml  # noqa: E402

GRAPH_DIR = os.path.join(ml.ROOT, "graphs")

INTRO = """# 젯코봇 동작 공유

동작 파일 하나 = `motions/` 안의 JSON 하나. 형식은 ROS2 `trajectory_msgs/JointTrajectory` 구조
(`joint_names`, `points[].positions` 라디안, `points[].time_from_start`) + 이름·로봇·상태 같은 정보.

**가장 쉬운 방법: `동작플레이어.sh` (처음 한 번 우클릭 → 프로그램으로 실행, 다음부터 바탕화면 아이콘)**
→ 브라우저에 목록·그래프, 버튼으로 RViz 재생 / 실제 로봇 재생 / 정지 / 손으로 따기.
실제 로봇은 이 PC 에서 SSH 로 움직임 (로봇에 설치할 것 없음). 팀 공용 키 `jetcobot-team.key` 를 다운로드 폴더에 두면 자동 인식.

| 하고 싶은 것 | 코드로 하는 방법 |
|---|---|
| 실제 로봇 재생 · 손으로 따기 | `웍질_재생.ipynb` (주피터) |
| RViz 에서 보기 | 노트북의 RViz 셀, 또는 `source /opt/ros/jazzy/setup.bash && python3 tools/play_rviz.py motions/<파일>.json` |
| 동작 올리기 | 노트북 `record()`/`save()` → `motions/` 에 저장 → GitHub 에 올리기 |

이 페이지는 `tools/make_index.py` 가 자동으로 만든다. 직접 고치지 말 것. 도구 설명은 README.md.

"""


def graph(path, m, pts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for fam in ("NanumGothic", "Noto Sans CJK KR", "UnDotum"):
        try:
            from matplotlib import font_manager
            font_manager.findfont(fam, fallback_to_default=False)
            plt.rcParams["font.family"] = fam
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False
    t = [p[0] for p in pts]
    fig, ax = plt.subplots(figsize=(7, 2.4), dpi=100)
    for j in range(6):
        ax.plot(t, [p[j + 1] for p in pts], lw=1.3, label=f"J{j + 1}")
    ax.set_xlabel("s")
    ax.set_ylabel("deg")
    ax.grid(alpha=0.3)
    ax.legend(ncol=6, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, 1.22), frameon=False)
    fig.tight_layout()
    os.makedirs(GRAPH_DIR, exist_ok=True)
    out = os.path.join(GRAPH_DIR, os.path.splitext(os.path.basename(path))[0] + ".png")
    fig.savefig(out)
    plt.close(fig)
    return os.path.relpath(out, ml.ROOT)


def make_index(quiet=False):
    rows, details = [], []
    for i, p in enumerate(ml._files(), 1):
        m, pts = ml.load(p)
        fn = os.path.relpath(p, ml.ROOT)
        rows.append(f"| {i} | {m.get('status', '')} | [{m['name']}](#{i}) | {m.get('robot', '')} | "
                    f"{pts[-1][0]:.1f}초 | {m.get('made_by', '')} | {m.get('author', '')} |")
        g = graph(p, m, pts)
        hint = m.get("play_hint", {})
        details.append(
            f"<a id=\"{i}\"></a>\n### {i}. {m['name']}\n\n"
            f"- 파일: [`{fn}`]({fn.replace(' ', '%20')})\n"
            f"- 상태: **{m.get('status', '')}** · 로봇: {m.get('robot', '')} · 길이 {pts[-1][0]:.1f}초 ({len(pts)}점)\n"
            f"- 만든 방법: {m.get('made_by', '')}\n"
            f"- 재생 권장: 속도 {hint.get('speed', '')}, 앞당김 {hint.get('lead', '')}초, {hint.get('hz', '')}Hz\n"
            + (f"- 메모: {m['notes']}\n" if m.get("notes") else "")
            + f"\n![{m['name']}]({g})\n")
    md = (INTRO + "## 동작 목록\n\n| # | 상태 | 이름 | 로봇 | 길이 | 만든 방법 | 만든 사람 |\n|---|---|---|---|---|---|---|\n"
          + "\n".join(rows) + "\n\n## 동작별 자세히\n\n" + "\n".join(details))
    with open(os.path.join(ml.ROOT, "MOTIONS.md"), "w", encoding="utf-8") as f:
        f.write(md)
    if not quiet:
        print(f"MOTIONS.md: 동작 {len(rows)}개")


if __name__ == "__main__":
    make_index()
