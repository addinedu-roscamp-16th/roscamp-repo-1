"""Shared helpers for the JetCobot 280 (myCobot 280) arm controllers: joint names, poses, UDP camera streamer."""
import json
import math
import socket

JOINTS = ['joint2_to_joint1', 'joint3_to_joint2', 'joint4_to_joint3', 'joint5_to_joint4', 'joint6_to_joint5',
          'joint6output_to_joint6']
REST = [0.0, 0.5, -1.9, 1.3, 0.0, 0.0]
# job -> (base yaw, reach pose). Yaw is relative to the arm base.
POSES = {
    'LOAD': (math.pi / 2, [0.0, -1.0, -0.6, -0.1, 0.0, 0.0]),
    'UNLOAD': (math.pi / 2, [0.0, -1.1, -0.5, 0.0, 0.0, 0.0]),
    'COLLECT_DISHES': (math.pi / 2, [0.0, -1.1, -0.5, 0.0, 0.0, 0.0]),
    'RETURN_DISHES': (math.pi / 2, [0.0, -1.0, -0.6, -0.1, 0.0, 0.0]),
    # [수정 2026-11-17] 조리 팔 자세 9개 삭제. 조리 팔은
    # frybot_arm/arm_motion.py 가 맡고, 여기는 서빙 팔 작업만 씀
}


def arm_pose(job, progress, t=0.0):
    """Joint angles for a job at progress 0..1 (rest -> reach -> rest)."""
    yaw, reach = POSES.get(job, (0.0, REST))
    k = math.sin(math.pi * min(max(progress, 0.0), 1.0))          # 0 -> 1 -> 0
    q = [REST[i] + (reach[i] - REST[i]) * k for i in range(6)]
    q[0] = yaw * min(1.0, k * 1.5)
    # [수정 2026-11-17] 웍 흔들기(STIR_FRY) 분기 삭제: 조리 팔 전용
    return q


class CameraStreamer:
    """Sends small JSON 'frames' to the AI server over UDP (stand-in for the real video stream)."""

    def __init__(self, camera_id, host='127.0.0.1', port=9100):
        self.camera_id, self.addr = camera_id, (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, kind, **data):
        try:
            self.sock.sendto(json.dumps(dict(camera=self.camera_id, kind=kind, **data)).encode(), self.addr)
        except OSError:
            pass
