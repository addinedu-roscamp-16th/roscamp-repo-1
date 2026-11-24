"""FryBot full system in the lightweight simulation.

  ros2 launch frybot_bringup sim.launch.py                       # RViz + all nodes
  ros2 launch frybot_bringup sim.launch.py planner:=cooperative_astar scheduler:=fifo_nearest rviz:=false

UIs:  http://localhost:8080 (reception / table / admin)   http://localhost:8090 (guest simulator)

[수정 2026-11-17] map_id:=<지도 이름> 으로 지도를 하나만 골라 띄움 (maps/ 의 폴더 이름)
  map_id:=proto          가상 매장 도면(기본값): 매장·손님·조리 팔까지 전부
  map_id:=test_map_v001  실측 지도: 관제 + 가상 로봇 + 그 지도만. 가상 매장용
                         노드와 화면은 띄우지 않음. 노드 간 이동만 지원
"""
import os
import re
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration as LC
from launch_ros.actions import Node

from frybot_arm.cooking import cooking_nodes
from frybot_bringup.sim_net import apply_sim_network
from frybot_bringup.urdf_tools import jetcobot_urdf, pinky_urdf
from frybot_control.layout import COOK_ARMS, Graph, m, robot_ids
from frybot_control.map_catalog import PROTO_MAP_ID, map_ids, profile
from frybot_mobile.navigator import params_file

ARM_SCALE = 0.3


def _nav2_displays(rid, show_global):
    """RViz group with what one robot's Nav2 sees and does: costmaps, footprint, lidar scan and the planned path."""
    def cmap(name, topic, on, alpha):
        return f"""        - Class: rviz_default_plugins/Map
          Name: {name}
          Enabled: {'true' if on else 'false'}
          Alpha: {alpha}
          Color Scheme: costmap
          Draw Behind: false
          Topic:
            Depth: 1
            Durability Policy: Transient Local
            History Policy: Keep Last
            Reliability Policy: Reliable
            Value: {topic}
          Update Topic:
            Depth: 5
            Durability Policy: Volatile
            History Policy: Keep Last
            Reliability Policy: Reliable
            Value: {topic}_updates
          Use Timestamp: false
          Value: {'true' if on else 'false'}
"""
    return f"""rviz_common/Group
      Name: Nav2 {rid}
      Enabled: true
      Displays:
{cmap('local costmap (lidar)', f'/{rid}/local_costmap/costmap', True, 0.6)}{cmap('global costmap (map)', f'/{rid}/global_costmap/costmap', show_global, 0.35)}        - Class: rviz_default_plugins/Polygon
          Name: footprint
          Enabled: true
          Alpha: 1
          Color: 25; 25; 255
          Topic:
            Depth: 5
            Durability Policy: Volatile
            History Policy: Keep Last
            Reliability Policy: Reliable
            Value: /{rid}/local_costmap/published_footprint
          Value: true
        - Class: rviz_default_plugins/LaserScan
          Name: scan
          Enabled: true
          Alpha: 1
          Color: 255; 0; 0
          Color Transformer: FlatColor
          Size (Pixels): 3
          Style: Points
          Topic:
            Depth: 5
            Durability Policy: Volatile
            History Policy: Keep Last
            Reliability Policy: Best Effort
            Value: /{rid}/scan
          Value: true
        - Class: rviz_default_plugins/Path
          Name: Nav2 plan
          Enabled: true
          Alpha: 1
          Color: 255; 0; 255
          Line Style: Billboards
          Line Width: 0.006
          Topic:
            Depth: 5
            Durability Policy: Volatile
            History Policy: Keep Last
            Reliability Policy: Reliable
            Value: /{rid}/plan
          Value: true
"""


# [수정 2026-11-17] 실측 지도 시뮬의 전역 코스트맵 표시(실기기와 같은 토픽)
def _global_costmap_display(rid, on):
    """RViz 의 전역 코스트맵 표시 항목 하나를 만든다.

    Args:
        rid: 로봇 이름.
        on: 처음부터 켜 둘지 여부.

    Returns:
        rviz 설정의 Displays 목록에 넣을 문자열.
    """
    topic = f'/{rid}/global_costmap/costmap'
    flag = 'true' if on else 'false'
    return f"""rviz_default_plugins/Map
      Name: {rid} global costmap
      Enabled: {flag}
      Alpha: 0.45
      Color Scheme: costmap
      Draw Behind: false
      Topic:
        Depth: 1
        Durability Policy: Transient Local
        History Policy: Keep Last
        Reliability Policy: Reliable
        Value: {topic}
      Update Topic:
        Depth: 5
        Durability Policy: Volatile
        History Policy: Keep Last
        Reliability Policy: Reliable
        Value: {topic}_updates
      Use Timestamp: false
      Value: {flag}
"""


# [수정 2026-11-17] store, focus, costmaps 인자 추가: 실측 지도에서는 가상 매장
# 표시(Store 마커, 조리 팔)를 빼고, 시점을 그 지도 가운데로 옮기고, 로봇별
# 전역 코스트맵 표시를 넣음
def rviz_config(robots, nav2=False, store=True, focus=None, costmaps=False):
    """RViz config with one robot + serving-arm display per AMR (the file on disk holds pinky1's as the template).
    With Nav2 driving, a 'Nav2 <robot>' group per AMR shows its costmaps, footprint, scan and plan.
    store=False leaves out the displays of the virtual store (store markers, cooking arms);
    focus=(x, y) moves the view centre there."""
    # [수정 2026-11-18] P2: RViz 설정 이름 frybot.rviz -> sim_store.rviz
    src = open(os.path.join(get_package_share_directory('frybot_bringup'),
                            'rviz', 'sim_store.rviz')).read()
    blocks = src.split('    - Class: ')
    out, base, arm, tail = [], None, None, ''
    for b in blocks:
        name = re.search(r'\n      Name: (\S+)', b)
        name = name.group(1) if name else ''
        if re.fullmatch(r'pinky\d+', name):
            base = base or b.replace(name, 'pinky1')
            if out[-1] != '@AMR@':
                out.append('@AMR@')
        elif re.fullmatch(r'pinky\d+_arm', name):
            arm = arm or b.replace(name[:-4], 'pinky1')
        elif not store and name in ('Store', 'cook_arm_a', 'cook_arm_b'):
            # 표시 항목(6칸 들여쓰기)만 버리고, 그 뒤에 이어진 설정은 남김
            lines = b.split('\n')[1:]
            rest = [k for k, ln in enumerate(lines)
                    if ln and not ln.startswith('      ')]
            if rest:
                tail += '\n'.join(lines[rest[0]:])
        else:
            out.append(b)
    amr = [base.replace('pinky1', r) for r in robots] + [arm.replace('pinky1', r) for r in robots]
    if nav2:
        amr += [_nav2_displays(r, i == 0) for i, r in enumerate(robots)]
    if costmaps:                               # 실기기 RViz 와 같이 모든 로봇 것을 켬
        amr += [_global_costmap_display(r, True) for r in robots]
    amr[-1] += tail
    i = out.index('@AMR@')
    out[i:i + 1] = amr
    text = '    - Class: '.join(out)
    if focus:
        text = re.sub(r'(Focal Point:\n\s+X: )\S+(\n\s+Y: )\S+',
                      lambda k: f'{k.group(1)}{focus[0]:.2f}{k.group(2)}{focus[1]:.2f}', text)
    path = os.path.join(tempfile.mkdtemp(prefix='frybot_rviz_'),
                        'sim_store.rviz')
    open(path, 'w').write(text)
    return path


# [수정 2026-11-17] 실측 지도 시뮬: 가상 매장용 노드(world, customer_ui,
# ai_server, 조리 팔)를 띄우지 않고 그 지도만 map_server 로 냄
def measured_nodes(map_id, robots, g, st):
    """실측 지도 한 장으로 도는 경량 시뮬의 노드 목록을 만든다.

    Args:
        map_id: maps/ 아래의 실측 지도 폴더 이름.
        robots: 로봇 이름 목록.
        g: 런치 인자 이름을 받아 값을 돌려주는 함수.
        st: 로봇 노드에 줄 시계 파라미터.

    Returns:
        런치 노드 목록.

    Raises:
        ValueError: 지도에 출발 노드가 없는 로봇이 있을 때.
    """
    graph = Graph(map_id)
    for rid in robots:                         # 출발 노드가 모자라면 여기서 멈춤
        graph.home_of(rid)
    drive, speed, guide = g('drive'), float(g('speed')), float(g('guide_speed'))
    nodes = [
        Node(package='frybot_control', executable='central_control', output='screen',
             parameters=[{'run_id': g('run_id'), 'scenario': g('scenario_name'), 'robot_ids': robots}]),
        Node(package='frybot_control', executable='task_manager', output='screen',
             parameters=[{'scheduler': g('scheduler'), 'planner': g('planner'), 'speed': speed, 'guide_speed': guide,
                          'robot_ids': robots, 'use_standby': g('standby') == 'true',
                          # [수정 2026-11-17] 실기기 런치와 같은 출발 노드
                          # 자동 이동(시뮬 로봇은 출발 노드에서 시작)
                          'auto_home': g('auto_home') == 'true',
                          # [수정 2026-11-18] W6: 계획 구간 지연(초)
                          'plan_overhead': float(g('plan_overhead'))}]),
        # [수정 2026-11-18] P1: web_service 기본이 실기기 값(관리자 명령은
        # 관제 PC 만)이 되어 시뮬은 예전 값을 명시
        Node(package='frybot_web', executable='web_service', output='screen',
             parameters=[{'admin_local_only': False,
                          # [수정 2026-11-18] P3: 매장 시뮬 상태 구독
                          'sim_world': True}]),
        Node(package='nav2_map_server', executable='map_server', output='screen',
             parameters=[{'yaml_filename': profile(map_id)['yaml']}]),
    ]
    # [수정 2026-11-17] 로봇별 전역 코스트맵: 실기기와 같은 nav2_store.yaml 값
    # (지도 + inflation)과 같은 토픽 /<로봇>/global_costmap/costmap. 시뮬에
    # 맞춘 것은 좌표계 이름과 지도 토픽뿐. 라이다가 없어 지역 코스트맵은 없음
    managed = ['map_server']
    for rid in robots:
        nodes.append(Node(
            package='nav2_costmap_2d', executable='nav2_costmap_2d', name='global_costmap',
            namespace=f'{rid}/global_costmap', output='screen',
            parameters=[params_file(rid, True, measured=True),
                        {'robot_base_frame': f'{rid}/base_footprint', 'static_layer.map_topic': '/map'}]))
        managed.append(f'/{rid}/global_costmap/global_costmap')
    nodes.append(Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name='lifecycle_manager_map',
                      output='screen', parameters=[{'autostart': True, 'bond_timeout': 0.0, 'node_names': managed}]))
    pinky, arm_small = pinky_urdf(), jetcobot_urdf(ARM_SCALE)
    for rid in robots:
        nodes += [
            # [수정 2026-11-18] P2(D2): 노드 이름 amr -> mobile_controller
            Node(package='frybot_mobile', executable='mobile_controller',
                 name='mobile_controller', namespace=rid, output='screen',
                 # [수정 2026-11-17] B3: 제어기 기본값이 실기기 값(nav2/tf)이
                 # 되어 시뮬은 위치 추정원(gz)을 명시
                 # [수정 2026-11-18] P1: base_frame 기본이 실기기 이름이 되어
                 # 시뮬(공유 /tf)은 접두어 붙은 이름을 명시
                 parameters=[{'robot_id': rid, 'drive': drive, 'pose_source': 'gz',
                              'base_frame': f'{rid}/base_footprint',
                              'speed': speed, 'guide_speed': guide}, st]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=rid,
                 parameters=[{'robot_description': pinky, 'frame_prefix': rid + '/'}, st]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=rid + '/arm',
                 parameters=[{'robot_description': arm_small, 'frame_prefix': rid + '_arm/'}, st]),
            Node(package='tf2_ros', executable='static_transform_publisher', name='arm_mount', namespace=rid,
                 arguments=['--x', '0.0', '--y', '0', '--z', '0.105', '--frame-id', rid + '/base_link',
                            '--child-frame-id', rid + '_arm/g_base']),
        ]
    xs, ys = zip(*graph.nodes.values())
    focus = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    nodes.append(Node(package='rviz2', executable='rviz2', condition=IfCondition(LC('rviz')),
                      arguments=['-d', rviz_config(robots, drive == 'nav2', store=False, focus=focus,
                                                   costmaps=True)]))
    return nodes


def setup(context):
    g = lambda k: LC(k).perform(context)
    # [수정 2026-11-17] A2: 통신 범위 설정을 sim_net 으로 옮김. 기본(net:=sim)은
    # 시뮬 전용 도메인이라 켜져 있는 Pinky 가 시뮬의 경로를 받지 않음
    apply_sim_network(g('net'), g('sim_domain'))
    drive, speed, guide = g('drive'), float(g('speed')), float(g('guide_speed'))
    st = {'use_sim_time': g('sim_time') == 'true'}
    ROBOTS = robot_ids(g('robots'))            # robots:=N -> pinky1..pinkyN (cooking arms are fixed)
    # [수정 2026-11-17] 지도를 하나만 골라 띄움. 인자가 없으면 환경 변수
    # FRYBOT_MAP_ID, 그것도 없으면 가상 매장 도면(proto)
    map_id = g('map_id') or os.environ.get('FRYBOT_MAP_ID', '') or PROTO_MAP_ID
    if map_id != PROTO_MAP_ID and map_id not in map_ids():
        raise ValueError(f'map_id:={map_id} 는 없는 지도입니다. '
                         f'쓸 수 있는 값: {[PROTO_MAP_ID] + map_ids()}')
    os.environ['FRYBOT_MAP_ID'] = map_id       # 아래 노드들이 이 값으로 지도를 고름
    measured = map_id != PROTO_MAP_ID
    if measured:
        return measured_nodes(map_id, ROBOTS, g, st)
    nodes = [
        Node(package='frybot_control', executable='central_control', output='screen',
             parameters=[{'run_id': g('run_id'), 'scenario': g('scenario_name'), 'qr_vacant_sec': float(g('qr_vacant_sec')),
                          'robot_ids': ROBOTS}]),
        Node(package='frybot_control', executable='task_manager', output='screen',
             parameters=[{'scheduler': g('scheduler'), 'planner': g('planner'), 'speed': speed, 'guide_speed': guide,
                          'cook_time_scale': float(g('cook_time_scale')), 'robot_ids': ROBOTS,
                          'use_standby': g('standby') == 'true',
                          # [수정 2026-11-18] P1: auto_home 기본이 켬(실기기 값)이
                          # 되어 가상 매장은 예전 값(끔)을 명시
                          'auto_home': False,
                          # [수정 2026-11-18] W6: 계획 구간 지연(초)
                          'plan_overhead': float(g('plan_overhead'))}]),
        # [수정 2026-11-18] P1: web_service 기본이 실기기 값(관리자 명령은
        # 관제 PC 만)이 되어 시뮬은 예전 값을 명시
        Node(package='frybot_web', executable='web_service', output='screen',
             parameters=[{'admin_local_only': False,
                          # [수정 2026-11-18] P3: 매장 시뮬 상태 구독
                          'sim_world': True}]),
        Node(package='frybot_sim', executable='ai_server', output='screen'),
        Node(package='frybot_sim', executable='world', output='screen'),
        Node(package='frybot_sim', executable='customer_ui', output='screen'),
    ]
    pinky = pinky_urdf()
    arm_small, arm_full = jetcobot_urdf(ARM_SCALE), jetcobot_urdf(1.0)
    for rid in ROBOTS:
        nodes += [
            # [수정 2026-11-18] P2(D2): 노드 이름 amr -> mobile_controller
            Node(package='frybot_mobile', executable='mobile_controller',
                 name='mobile_controller', namespace=rid, output='screen',
                 # [수정 2026-11-17] B3: 시뮬은 위치 추정원(gz)을 명시
                 # [수정 2026-11-18] P1: base_frame 기본이 실기기 이름이 되어
                 # 시뮬(공유 /tf)은 접두어 붙은 이름을 명시
                 parameters=[{'robot_id': rid, 'drive': drive, 'pose_source': 'gz',
                              'base_frame': f'{rid}/base_footprint',
                              'speed': speed, 'guide_speed': guide}, st]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=rid,
                 parameters=[{'robot_description': pinky, 'frame_prefix': rid + '/'}, st]),
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=rid + '/arm',
                 parameters=[{'robot_description': arm_small, 'frame_prefix': rid + '_arm/'}, st]),
            Node(package='tf2_ros', executable='static_transform_publisher', name='arm_mount', namespace=rid,
                 arguments=['--x', '0.0', '--y', '0', '--z', '0.105', '--frame-id', rid + '/base_link',
                            '--child-frame-id', rid + '_arm/g_base']),
        ]
    # [수정 2026-11-17] 조리 팔은 frybot_sim 대신 frybot_arm 패키지
    # (Master Controller + Arm Controller A/B)
    nodes += cooking_nodes(tuple(COOK_ARMS),
                           undercooked_prob=float(g('undercooked_prob')))
    for arm_id, info in COOK_ARMS.items():
        x, y = m(*info['pos_cm'])
        nodes += [
            Node(package='robot_state_publisher', executable='robot_state_publisher', namespace=arm_id,
                 parameters=[{'robot_description': arm_full, 'frame_prefix': arm_id + '/'}]),
            Node(package='tf2_ros', executable='static_transform_publisher', name='base_tf', namespace=arm_id,
                 arguments=['--x', str(x), '--y', str(y), '--z', '0.0', '--yaw', '3.14159', '--frame-id', 'map',
                            '--child-frame-id', arm_id + '/g_base']),
        ]
    nodes.append(Node(package='rviz2', executable='rviz2', condition=IfCondition(LC('rviz')),
                      arguments=['-d', rviz_config(ROBOTS, drive == 'nav2')]))
    return nodes


def generate_launch_description():
    args = [('scheduler', 'min_cost_eta_rh'), ('planner', 'sipp'), ('rviz', 'true'), ('drive', 'kinematic'),
            ('speed', '0.08'), ('guide_speed', '0.05'), ('cook_time_scale', '20.0'), ('qr_vacant_sec', '8.0'),
            ('undercooked_prob', '0.25'), ('run_id', ''), ('standby', 'true'), ('sim_time', 'false'), ('scenario_name', 'interactive'),
            # [수정 2026-11-17] A2: net 기본값 lan -> sim (시뮬 전용 도메인
            # sim_domain). 시뮬의 관제와 /pinky1..3 이 실기기와 같은 도메인(73)에
            # 보이면 켜져 있는 Pinky 가 시뮬의 경로를 주행할 수 있음.
            # 다른 터미널의 ros2 명령은 export ROS_DOMAIN_ID=74 뒤에 실행
            ('robots', '3'), ('net', 'sim'), ('sim_domain', '74'), ('map_id', ''),
            ('auto_home', 'true'),
            # [수정 2026-11-18] W6: 계획의 구간 지연(초). 경량 시뮬의 로봇은
            # 지연 없이 움직이므로 0.0
            ('plan_overhead', '0.0')]
    return LaunchDescription([DeclareLaunchArgument(k, default_value=v) for k, v in args] + [OpaqueFunction(function=setup)])
