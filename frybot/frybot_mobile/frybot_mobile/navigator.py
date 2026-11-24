"""FrybotNavigator: builds the Nav2 stack of one FrybotMobile (shared by navigator.launch.py, robot.launch.py and the
simulation bring-up)."""
import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node

NAV_NODES = ['controller_server', 'planner_server', 'bt_navigator', 'docking_server']
LOC_NODES = ['map_server', 'amcl']


def params_file(rid, real, map_yaml='', measured=False):
    """Fill the placeholders of nav2_store.yaml for one robot and return the path of the result."""
    share = get_package_share_directory('frybot_mobile')
    body = open(os.path.join(share, 'config', 'nav2_store.yaml')).read()
    for k, v in (('__NS__', rid), ('__FP__', '' if real else rid + '/'), ('__SIM__', 'false' if real else 'true'),
                 ('__BT__', os.path.join(share, 'config', 'segment_bt.xml')), ('__MAPTOPIC__', f'/{rid}/map' if real else '/map'), ('__MAP__', map_yaml),
                 ('__GLOBAL_INFLATION__', '0.07' if real and measured else '0.08')):
        body = body.replace(k, v)
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_nav2_'), rid + '_nav2.yaml')
    # the nodes run in the robot's namespace, so the parameter file needs the namespace as its root key
    open(path, 'w').write(rid + ':\n' + ''.join('  ' + ln if ln.strip() else ln for ln in body.splitlines(True)))
    return path


# [수정 2026-11-18] P1: real 의 기본값(False, 시뮬)을 없애 부르는 쪽이 실기기/
# 시뮬을 반드시 밝히게 함
# [수정 2026-11-18] T-38: 실측 지도에는 도크가 없어(layout.docks() 가 빈
# 값) docking_server 와 aruco_dock_detector 를 띄우지 않음(로봇당 프로세스
# 2개 감소). 가상 매장 도면은 그대로 띄움
def navigator_nodes(rid, real, map_yaml='', measured=False, initial_pose=()):
    """Launch actions of one robot's Nav2 stack (also used by the simulation bring-up)."""
    docking = not measured
    pfile = params_file(rid, real, map_yaml, measured=measured)
    # on the robot every node of the namespace shares the robot's own TF topics
    remap = [('/tf', 'tf'), ('/tf_static', 'tf_static')] if real else []
    common = dict(namespace=rid, output='screen', parameters=[pfile], remappings=remap)
    controller = dict(common)
    # [수정 2026-11-17] 실측 지도는 FollowPath 만 전진 전용으로 덮어씀.
    # 후진용 FollowPathReverse 는 nav2_store.yaml 값 그대로 (UR-03 안내 후진)
    if measured:
        controller['parameters'] = [pfile, {'FollowPath.use_rotate_to_heading': True,
                                              'FollowPath.allow_reversing': False}]
    nodes = [
        Node(package='nav2_controller', executable='controller_server', **controller),
        Node(package='nav2_planner', executable='planner_server', **common),
        Node(package='nav2_bt_navigator', executable='bt_navigator', **common),
    ]
    dock_nodes = [
        Node(package='opennav_docking', executable='opennav_docking', name='docking_server', **common),
        # ArUco marker -> dock pose for the docking server (camera image only used while docking)
        Node(package='frybot_mobile', executable='aruco_dock_detector', namespace=rid, output='screen', remappings=remap,
             # [수정 2026-11-18] P1: 검출기 프레임 기본값이 실기기 이름이 되어
             # 시뮬(공유 /tf)일 때만 '<로봇>/...' 를 넘김
             parameters=[{'robot_id': rid}] +
                        ([] if real else [{'base_frame': f'{rid}/base_footprint',
                                           'camera_frame': f'{rid}/front_camera_link',
                                           'fixed_frame': f'{rid}/odom'}])),
    ]
    nav_names = [n for n in NAV_NODES if docking or n != 'docking_server']
    nodes += (dock_nodes if docking else []) + [
        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager', namespace=rid,
             output='screen', parameters=[{'use_sim_time': not real, 'autostart': True, 'bond_timeout': 0.0,
                                           'node_names': nav_names}]),
    ]
    if real:
        amcl = dict(common)
        if initial_pose:
            x, y, yaw = initial_pose
            amcl['parameters'] = [pfile, {'set_initial_pose': True, 'initial_pose.x': x,
                                         'initial_pose.y': y, 'initial_pose.yaw': yaw}]
        nodes = [
            Node(package='nav2_map_server', executable='map_server', **common),
            Node(package='nav2_amcl', executable='amcl', **amcl),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_localization',
                 namespace=rid, output='screen', parameters=[{'use_sim_time': False, 'autostart': True,
                                                              'bond_timeout': 0.0, 'node_names': LOC_NODES}]),
        ] + nodes
    return nodes
