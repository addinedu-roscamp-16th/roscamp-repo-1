#!/usr/bin/env python3
"""동작 파일을 RViz 에서 재생 (ROS2 Jazzy)

  source /opt/ros/jazzy/setup.bash
  python3 tools/play_rviz.py motions/<동작>.json [<동작2>.json ...] [--rate 0.5] [--loop] [--no-rviz] [--scene 이름|robot]

장면: 동작 파일의 "scene"(예: kitchen_table_wok_v2, scenes/ 폴더) + "mount"(robot1/robot2) 를 기본으로 씀.
      --scene robot = 로봇 팔만 (robot/), --scene <이름> = 다른 장면으로

하는 일: 같이 넣어 둔 로봇 URDF(robot/) 로 robot_state_publisher + RViz 를 띄우고
        동작 파일의 각도를 /joint_states 로 30Hz 보냄 → RViz 속 로봇이 움직임.
다른 ROS 프로그램(MoveIt 등)과 섞이지 않게 기본 ROS_DOMAIN_ID=55, 이 PC 안에서만 통신.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROBOT_DIR = os.path.join(ROOT, "robot")


def load(path):
    m = json.load(open(path, encoding="utf-8"))
    pts = []
    for p in m["points"]:
        t = p["time_from_start"]
        sec = t["sec"] + t["nanosec"] * 1e-9 if isinstance(t, dict) else float(t)
        pts.append((sec, p["positions"]))
    return m, pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--loop", action="store_true", help="끝나면 처음부터 반복 (RViz 창 닫으면 끝)")
    ap.add_argument("--no-rviz", action="store_true", help="RViz 창 없이 (시험용)")
    ap.add_argument("--mount", default="", help="장면 속 로봇 자리 robot1/robot2. 비우면 동작 파일에 적힌 자리")
    ap.add_argument("--scene", default="", help="장면 이름 (scenes/<이름>) 또는 robot. 비우면 동작 파일에 적힌 장면")
    a = ap.parse_args()

    import signal
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))   # 꺼질 때 자식 정리
    env = dict(os.environ)
    # 재생마다 다른 ROS 도메인 (60~99) → 남은 프로그램·다른 재생과 섞이지 않음
    env["ROS_DOMAIN_ID"] = os.environ.get("MOTION_RVIZ_DOMAIN", str(60 + os.getpid() % 40))
    env["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
    os.environ.update(env)

    motions = [load(f) for f in a.files]
    scene = a.scene or motions[0][0].get("scene", "") or "robot"
    sdir = os.path.join(ROOT, "scenes", scene)
    if scene != "robot" and not os.path.isfile(os.path.join(sdir, "scene.urdf")):
        print(f"장면 '{scene}' 이 없어 로봇 팔만 보여 줍니다.", flush=True)
        scene = "robot"
    if scene == "robot":
        urdf = open(os.path.join(ROBOT_DIR, "mycobot280_gripper.urdf"), encoding="utf-8").read()
        urdf = urdf.replace('filename="meshes/', f'filename="file://{ROBOT_DIR}/meshes/')
        frame, focal, dist, all_joints = "g_base", (0.05, 0, 0.18), 0.9, {}
    else:
        info = json.load(open(os.path.join(sdir, "scene.json"), encoding="utf-8"))
        urdf = open(os.path.join(sdir, "scene.urdf"), encoding="utf-8").read()
        urdf = urdf.replace('filename="meshes/', f'filename="file://{sdir}/meshes/')
        frame, focal, dist, all_joints = info.get("fixed_frame", "world"), (0.53, 0.42, 0.15), 1.5, info["joints"]
    print(f"장면: {scene}", flush=True)
    own = os.path.join(sdir, "scene.rviz") if scene != "robot" else ""
    rviz_cfg = open(own if own and os.path.isfile(own) else os.path.join(ROBOT_DIR, "motion.rviz"),
                    encoding="utf-8").read()     # 장면에 맞춘 RViz 설정(시점)이 있으면 그것
    rviz_cfg = (rviz_cfg.replace("Fixed Frame: g_base", f"Fixed Frame: {frame}")
                .replace("Distance: 0.9", f"Distance: {dist}")
                .replace("X: 0.05\n        Y: 0\n        Z: 0.18", f"X: {focal[0]}\n        Y: {focal[1]}\n        Z: {focal[2]}"))
    rviz_path = os.path.join("/tmp", f"motion_share_{os.getpid()}.rviz")
    open(rviz_path, "w", encoding="utf-8").write(rviz_cfg)
    params = os.path.join("/tmp", f"motion_share_rsp_{os.getpid()}.yaml")
    with open(params, "w") as f:
        json.dump({"robot_state_publisher": {"ros__parameters": {"robot_description": urdf}}}, f)

    rsp = "/opt/ros/jazzy/lib/robot_state_publisher/robot_state_publisher"   # ros2 run 을 거치지 않아야 끌 때 같이 꺼짐
    procs = [subprocess.Popen([rsp, "--ros-args", "--params-file", params], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
    if not a.no_rviz:
        rlog = open(os.path.join("/tmp", f"motion_share_rviz_{os.getuid()}.log"), "w")
        procs.append(subprocess.Popen(["rviz2", "-d", rviz_path], env=env, stdout=rlog, stderr=subprocess.STDOUT))

    import rclpy
    from sensor_msgs.msg import JointState
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)   # 끄기 신호는 위의 정리 코드가 받음
    node = rclpy.create_node("motion_share_player")
    pub = node.create_publisher(JointState, "/joint_states", 10)
    if scene == "robot":
        names, rest = motions[0][0]["joint_names"], ([], [])
    else:                                                   # 장면 속 해당 로봇 자리 관절 + 나머지 로봇은 0°
        mount = a.mount or motions[0][0].get("mount") or info["mounts"][-1]
        if mount not in all_joints:
            mount = info["mounts"][-1]
        names = all_joints[mount]
        others = [j for m, js in all_joints.items() if m != mount for j in js]
        rest = (others, [0.0] * len(others))

    def send(pos):
        msg = JointState()
        msg.header.stamp = node.get_clock().now().to_msg()
        msg.name, msg.position = list(names) + rest[0], list(pos) + rest[1]
        pub.publish(msg)

    def alive():
        return a.no_rviz or procs[-1].poll() is None

    try:
        first = motions[0][1][0][1]
        t_hold = time.time()
        while time.time() - t_hold < (1.0 if a.no_rviz else 4.0) and alive():   # RViz 뜨는 동안 시작 자세
            send(first)
            time.sleep(1 / 30)
        while alive():
            for m, pts in motions:
                print(f"▶ {m['name']} ({pts[-1][0]:.1f}초, ×{a.rate})", flush=True)
                t0, i = time.time(), 0
                while alive():
                    t = (time.time() - t0) * a.rate
                    while i + 1 < len(pts) and pts[i + 1][0] <= t:
                        i += 1
                    if i + 1 >= len(pts):
                        send(pts[-1][1])
                        break
                    (ta, pa), (tb, pb) = pts[i], pts[i + 1]
                    f = (t - ta) / max(tb - ta, 1e-6)
                    send([x + (y - x) * f for x, y in zip(pa, pb)])
                    time.sleep(1 / 30)
                time.sleep(0.8)
            if not a.loop:
                print("■ 재생 끝 (RViz 창을 닫으면 종료, 다시 보려면 --loop)", flush=True)
                while alive() and not a.no_rviz:      # 마지막 자세 유지
                    send(motions[-1][1][-1][1])
                    time.sleep(0.2)
                break
    except (KeyboardInterrupt, Exception):
        pass
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()
        try:
            node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass
        for f in (params, rviz_path):
            try:
                os.remove(f)
            except OSError:
                pass


if __name__ == "__main__":
    main()
