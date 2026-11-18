"""Launch actions that start the registered robots over SSH.

See robot_remote.py and the registry ~/.config/frybot/robots.yaml.
[수정 2026-11-18] P2: 등록부 위치를 실제 경로로(예전 config/robots.yaml).
"""
import os

from ament_index_python.packages import get_package_prefix
from launch.actions import ExecuteProcess, LogInfo

from .robot_remote import load_registry, registry_file, registry_missing


def registered(robots_file=''):
    """Enabled robots of the registry, {} when there is no usable registry."""
    try:
        return load_registry(robots_file)
    except (OSError, ValueError):
        return {}


# [수정 2026-11-18] T-30: remote 기동인데 등록부가 없으면 아무 말 없이
# 관제만 뜨던 것을, 같은 동작에 안내 로그를 남기도록 함
def registry_notice(robots_file: str = '') -> list:
    """등록부가 없을 때 런치에 넣을 안내 로그를 돌려준다.

    Args:
        robots_file: 런치의 robots_file 인자.

    Returns:
        등록부가 있으면 빈 목록, 없으면 LogInfo 하나가 든 목록.
    """
    missing = registry_missing(robots_file)
    if not missing:
        return []
    return [LogInfo(msg=missing + ' -> 로봇 쪽은 기동하지 않음')]


def pick_robots(arg, reg):
    """Robot ids for a launch: 'pinky1,pinky3' = exactly these, '2' = pinky1..pinky2, '' = all registered ones."""
    from frybot_control.layout import robot_ids
    arg = arg.strip()
    if arg and not arg.isdigit():
        return [s.strip() for s in arg.split(',') if s.strip()]
    if arg:
        return robot_ids(arg)
    return list(reg) or robot_ids(1)


def fleet_rviz_config(robot_ids):
    """RViz config for exactly these robots, made from rviz/fleet.rviz (which is written for pinky1 and pinky2):
    one display group per robot (global / local costmap, footprint, model) and one "2D Pose Estimate" tool per robot
    (in robot order) that publishes on /<robot>/initialpose for that robot's AMCL."""
    import tempfile
    from ament_index_python.packages import get_package_share_directory
    # [수정 2026-11-18] P2: RViz 설정 이름 fleet_real.rviz -> fleet.rviz
    text = open(os.path.join(get_package_share_directory('frybot_bringup'),
                             'rviz', 'fleet.rviz')).read()
    mark, tail_mark, tools = '  - Class: rviz_common/Group\n', '  - Class: rviz_default_plugins/MarkerArray\n', '  Tools:\n'
    head, rest = text.split(mark, 1)
    group = mark + rest.split(mark, 1)[0]
    tail = tail_mark + text.split(tail_mark, 1)[1]
    pose = ''.join(f'  - Class: rviz_default_plugins/SetInitialPose\n    Covariance x: 0.02\n    Covariance y: 0.02\n'
                   f'    Covariance yaw: 0.03\n    Topic:\n      Depth: 5\n      Durability Policy: Volatile\n'
                   f'      History Policy: Keep Last\n      Reliability Policy: Reliable\n'
                   f'      Value: /{rid}/initialpose\n' for rid in robot_ids)
    before, after = tail.split(tools, 1)
    out = head.replace('pinky1', robot_ids[0]) + ''.join(group.replace('pinky1', rid) for rid in robot_ids) + \
        before + tools + after.replace('  Views:\n', pose + '  Views:\n', 1)
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_fleet_rviz_'), 'fleet.rviz')
    with open(path, 'w') as stream:
        stream.write(out)
    return path


def start_poses(arg, map_id):
    """'pinky1:A2,pinky3:W3:90' -> {'pinky1': 'x y yaw', ...}: where each robot stands at start, as a roadmap node
    and an optional heading in degrees (0 = +x of the map). Given to AMCL as the initial pose."""
    import math
    from frybot_control.layout import Graph
    out = {}
    graph = Graph(map_id) if arg.strip() else None
    for item in arg.split(','):
        if not item.strip():
            continue
        parts = item.strip().split(':')
        if len(parts) < 2 or parts[1] not in graph.nodes:
            raise ValueError(f'poses: "{item}" must be robot:node[:heading_deg] with a node of the map')
        x, y = graph.nodes[parts[1]]
        yaw = math.radians(float(parts[2])) if len(parts) > 2 else 0.0
        out[parts[0]] = f'{x:.3f} {y:.3f} {yaw:.3f}'
    return out


# [수정 2026-11-18] T-38: 관제 PC 가 탐색 상대로 삼을 로봇 주소 목록
def static_peers(robot_ids: list, reg: dict) -> str:
    """관제 PC 의 ROS_STATIC_PEERS 값을 만든다.

    Args:
        robot_ids: 이번 런치에 든 로봇 이름.
        reg: load_registry 가 돌려준 등록부.

    Returns:
        터미널에 있던 ROS_STATIC_PEERS 값 뒤에 등록된 로봇의 host 를
        ';' 로 이은 문자열. 없으면 빈 문자열.
    """
    hosts = [str(reg[rid]['host']) for rid in robot_ids if rid in reg]
    old = os.environ.get('ROS_STATIC_PEERS', '')
    return ';'.join(([old] if old else []) + hosts)


# [수정 2026-11-18] map_yaml 인자(--map)를 지움(사용자 결정). 다른 yaml 을
# 끼우면 roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에 새 map_id
# 로 추가
# [수정 2026-11-18] T-38: discovery 인자를 robot_remote 에 넘김
def remote_bringup(robot_ids, map_id='', robots_file='', poses=None,
                   discovery='peers'):
    """One SSH bring-up process per robot. Ctrl-C on the launch stops the robots too."""
    reg = registered(robots_file)
    exe = os.path.join(get_package_prefix('frybot_bringup'), 'lib', 'frybot_bringup', 'robot_remote')
    acts = []
    for rid in robot_ids:
        if rid not in reg:
            acts.append(LogInfo(msg=f'{rid} is not in {registry_file(robots_file)}: start it on the robot by hand'))
            continue
        cmd = [exe, rid]
        if map_id:
            cmd += ['--map-id', map_id]
        if robots_file:
            cmd += ['--robots-file', robots_file]
        if poses and rid in poses:
            cmd += ['--arg', f'initial_pose:={poses[rid]}']
        cmd += ['--discovery', discovery]
        acts.append(ExecuteProcess(cmd=cmd, name=f'remote_{rid}', output='screen', emulate_tty=True,
                                   sigterm_timeout='100', sigkill_timeout='20'))
    return acts
