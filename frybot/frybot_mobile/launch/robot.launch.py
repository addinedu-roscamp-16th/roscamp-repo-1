"""Everything that runs ON one real Pinky Pro for FryBot: the robot's own drivers, FrybotNavigator and the
FrybotMobile Controller, all in the robot's namespace.

  ros2 launch frybot_mobile robot.launch.py robot_id:=pinky1 \
      map_id:=test_map_v001

[수정 2026-11-18] D7: map_id:= 는 필수(real.launch.py 의 B4 와 같음).
없으면 쓸 수 있는 지도 이름을 안내하고 멈춤. 예전에는 map:= 만 주면
그래프가 가상 매장 도면(proto)으로 조용히 떴음.
[수정 2026-11-18] map:= 인자를 지움(사용자 결정). 다른 yaml 을 끼우면
roadmap.json 과 지도 이미지가 어긋남. 필요하면 maps/ 에 새 map_id 로 추가.

Start the robot on its home spot (charger of that robot), facing into the store (+x). The central PC runs
`ros2 launch frybot_bringup real.launch.py` with the same ROS_DOMAIN_ID.
  drivers:=false   the Pinky drivers are already running in this namespace
  drivers:=pinky_pro   use the external pinky_bringup (bringup_robot.launch.xml) as before 2026-11-17
  ai_host:=<ip>    address of the AI server (camera stream stand-in), default: none
  guest_track_required:=false   [수정 2026-11-17] G4: 기본 true. 손님 추적 값이 없어도 안내를 출발(시험용)
"""
import os
import subprocess

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription, OpaqueFunction, SetEnvironmentVariable
from launch.launch_description_sources import AnyLaunchDescriptionSource, PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node, PushRosNamespace, SetRemap

from frybot_control.layout import Graph
from frybot_control.map_catalog import map_ids, profile


# [수정 2026-11-17] pinky_pro 의존 제거: 모터·배터리 드라이버는 frybot_mobile,
# 로봇 모델은 frybot_description 의 사본을 씀. 구성은 pinky_bringup 의
# bringup_robot.launch.xml 과 같음. drivers:=pinky_pro 는 이전 방식(되돌리기용)
# [수정 2026-11-18] T-37: 모터·라이다 포트를 인자로 받음(기본은 로봇에 설치된
# pinky_bringup 과 같은 /dev/ttyAMA5, /dev/ttyS0. 11-17 사본은 다른 버전의
# /dev/ttyAMA4, /dev/ttyAMA0 이라 모터·라이다가 뜨지 않았음)
def driver_actions(mode: str, motor_port: str = '/dev/ttyAMA5',
                   lidar_port: str = '/dev/ttyS0') -> list:
    """로봇 네임스페이스 안에서 띄울 Pinky 드라이버 액션을 만든다.

    Args:
        mode: 'pinky_pro' 이면 외부 pinky_bringup 의 런치를 포함하고,
            그 밖에는 frybot 안의 드라이버를 띄운다.
        motor_port: 모터(다이나믹셀) 직렬 포트. frybot 드라이버에만 씀.
        lidar_port: 라이다 직렬 포트. frybot 드라이버에만 씀.

    Returns:
        GroupAction 에 넣을 launch 액션 목록.
    """
    if mode == 'pinky_pro':
        return [IncludeLaunchDescription(AnyLaunchDescriptionSource(
            os.path.join(get_package_share_directory('pinky_bringup'),
                         'launch', 'bringup_robot.launch.xml')))]
    xacro_file = os.path.join(
        get_package_share_directory('frybot_description'),
        'pinky', 'urdf', 'robot.urdf.xacro')
    urdf = subprocess.check_output(
        ['xacro', xacro_file, 'namespace:=', 'is_sim:=false',
         'cam_tilt_deg:=0']).decode()
    lidar_launch = os.path.join(
        get_package_share_directory('sllidar_ros2'), 'launch',
        'sllidar_c1_launch.py')
    return [
        Node(package='robot_state_publisher',
             executable='robot_state_publisher', name='robot_state_publisher',
             parameters=[{'ignore_timestamp': False, 'use_sim_time': False,
                          'robot_description': urdf, 'frame_prefix': ''}]),
        Node(package='joint_state_publisher',
             executable='joint_state_publisher', name='joint_state_publisher',
             output='screen',
             parameters=[{'source_list': ['joint_states'], 'rate': 20.0,
                          'use_sim_time': False}]),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(lidar_launch),
            launch_arguments={
                'serial_port': lidar_port, 'frame_id': 'rplidar_link',
                'inverted': 'false', 'angle_compensate': 'true',
                'scan_mode': 'DenseBoost'}.items()),
        Node(package='frybot_mobile', executable='pinky_driver',
             parameters=[{'wheel_radius': 0.027,
                          'wheel_separation': 0.0961,
                          'serial_port': motor_port}]),
        Node(package='frybot_mobile', executable='pinky_battery'),
    ]


def setup(context):
    g = lambda k: LC(k).perform(context)
    rid = g('robot_id')
    map_id = g('map_id')
    # [수정 2026-11-18] D7: map_id 필수. 지도 없이 가상 매장 그래프로 뜨지
    # 않게 함
    if not map_id:
        raise ValueError('robot.launch.py 에는 map_id:= 가 필요합니다. '
                         f'쓸 수 있는 값: {map_ids()}')
    # [수정 2026-11-18] map:= 를 지워 "둘 중 하나만" 검사도 지움
    Graph(map_id).home_of(rid)
    map_yaml = profile(map_id)['yaml']
    acts = [SetEnvironmentVariable('FRYBOT_MAP_ID', map_id)]
    if g('drivers') != 'false':
        # the drivers have no namespace argument: push the namespace and give the robot its own TF topics, so that
        # several robots can share one ROS domain (frames stay plain: odom, base_footprint, rplidar_link)
        acts.append(GroupAction([
            PushRosNamespace(rid), SetRemap('/tf', 'tf'), SetRemap('/tf_static', 'tf_static')] +
            driver_actions(g('drivers'), g('motor_port'), g('lidar_port'))))
    acts.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(get_package_share_directory('frybot_mobile'), 'launch',
                                                   'navigator.launch.py')),
        launch_arguments={'robot_id': rid, 'mode': 'real', 'map': map_yaml, 'map_id': map_id,
                          'initial_pose': g('initial_pose')}.items()))
    # [수정 2026-11-18] P2(D2): 노드 이름 amr -> mobile_controller
    acts.append(Node(package='frybot_mobile', executable='mobile_controller',
                     name='mobile_controller', namespace=rid, output='screen',
                     remappings=[('/tf', 'tf'), ('/tf_static', 'tf_static')],
                     parameters=[{'robot_id': rid, 'drive': 'nav2', 'pose_source': 'tf', 'base_frame': 'base_footprint',
                                  'battery_topic': f'/{rid}/battery/percent', 'speed': float(g('speed')),
                                  'guide_speed': float(g('guide_speed')), 'ai_host': g('ai_host'),
                                  # [수정 2026-11-17] G4: 실기기는 손님 추적
                                  # (/frybot/guest_track)이 없으면 안내 구간을
                                  # 출발하지 않음(사람 옆에서 후진하는 동작)
                                  'guest_track_required':
                                      g('guest_track_required') == 'true'}]))
    return acts


def generate_launch_description():
    args = [('robot_id', 'pinky1'), ('map_id', ''), ('drivers', 'true'), ('speed', '0.08'), ('guide_speed', '0.05'),
            ('ai_host', '127.0.0.1'), ('initial_pose', ''),
            # [수정 2026-11-18] T-37: 모터·라이다 직렬 포트
            ('motor_port', '/dev/ttyAMA5'), ('lidar_port', '/dev/ttyS0'),
            ('guest_track_required', 'true')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] +
                             [OpaqueFunction(function=setup)])
