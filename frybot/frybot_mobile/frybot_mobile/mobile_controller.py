"""FrybotMobile Controller: the software of one AMR (Pinky Pro + serving arm). Components from the SW architecture:
FrybotMobile Controller (NavigateRoute action, status), FrybotNavigator client (one Nav2 goal per granted segment),
FrybotMobile Arm Controller (ArmJob action), Camera Streamer (UDP).
  drive:=kinematic  moves the pose directly (lightweight simulation)
  drive:=nav2       every granted roadmap segment is a Nav2 NavigateToPose goal (global + local costmap, lidar)
  drive:=cmd_vel    straight-line cmd_vel/odom driving without costmaps (kept for comparison)
  pose_source:=gz   pose from the simulator's true model pose; this node publishes map -> odom (simulation)
  pose_source:=tf   pose from TF map -> base_frame, i.e. from AMCL (real robot); sends AMCL the initial pose
[수정 2026-11-17] B3: 기본값은 실기기 값(drive=nav2, pose_source=tf). 시뮬 런치가 kinematic / gz 를 명시함.
[수정 2026-11-18] P1: base_frame 기본도 실기기 값(base_footprint).
로봇에서 런치 없이 단독 실행할 때는 /tf 리맵(/tf -> tf,
/tf_static -> tf_static)과 FRYBOT_MAP_ID 가 필요(robot.launch.py 참고).
Precise docking: when a route ends on a dock (charger, pick-up spot, dish return, table stop: layout.docks()), the
last segment is not a Nav2 goal. From the node before the dock the robot turns to the dock heading, the Nav2 docking
server drives it onto the dock pose (on the ArUco wall marker where there is one), and the heading is trimmed.
The serving arm and the camera are still stand-ins (timed arm jobs, JSON "frames") in both cases.
"""
import math
import threading
import time

import rclpy
# [수정 2026-11-18] P3: TransformStamped·TFMessage·json 은 sim_backend 로 옮김
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry
from nav2_msgs.action import DockRobot, NavigateToPose
from nav2_msgs.msg import SpeedLimit
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.action import ActionClient
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import DurabilityPolicy
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState, LaserScan
from std_msgs.msg import Float32, Int32, String
from tf2_ros import Buffer, TransformException
from tf2_ros import TransformListener

from frybot_control.layout import Graph, docks
# [수정 2026-11-18] P1(D1): 지도 이름 없이 뜨지 않음
from frybot_control.map_catalog import require_map_id
from frybot_interfaces.action import ArmJob, NavigateRoute
from frybot_interfaces.msg import ArmStatus, FleetHeartbeat, GuestTrack
from frybot_interfaces.msg import RobotStatus, TrafficGrant

from .arm_common import JOINTS, REST, CameraStreamer, arm_pose
from .sim_backend import SimBackend  # [수정 2026-11-18] P3(D6)

QOS = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# [수정 2026-11-18] P2(D2): 클래스·노드 이름을 실행 파일과 같게(예전 Amr, amr)
class MobileController(Node):
    """AMR 한 대의 제어기(NavigateRoute·ArmJob 액션, 상태 보고)."""

    def __init__(self):
        super().__init__('mobile_controller')
        require_map_id('mobile_controller')  # [수정 2026-11-18] P1(D1)
        p = self.declare_parameter
        self.rid = p('robot_id', 'pinky1').value
        self.speed, self.guide_speed = p('speed', 0.08).value, p('guide_speed', 0.05).value
        self.turn_rate = p('turn_rate', 2.5).value
        # [수정 2026-11-17] B3: 기본값을 시뮬 값(kinematic, gz)에서 실기기 값
        # 으로 바꿈. 파라미터 없이 로봇에서 실행하면 움직이지 않고 경로를
        # "성공"으로 끝내던 것을 막음
        self.drive = p('drive', 'nav2').value
        self.pose_source = p('pose_source', 'tf').value
        # [수정 2026-11-17] D4: 위치 추정(TF map -> base) 신선도 감시.
        # tf_stale_sec 보다 오래된 변환은 쓰지 않고, 새 변환이 이 시간 넘게
        # 없으면 주행을 세우고 SENSOR_ERROR 를 보고(0 이하면 감시 안 함)
        self.tf_stale = p('tf_stale_sec', 1.0).value
        self.tf_ok = False           # 가장 최근 조회에서 새 변환을 받았는지
        # [수정 2026-11-18] P1: 기본을 실기기 프레임 이름으로. 시뮬 런치가
        # '<로봇>/base_footprint' 를 명시함
        self.base_frame = p('base_frame', 'base_footprint').value
        battery_topic = p('battery_topic', '').value          # real Pinky: battery/percent (std_msgs/Float32)
        # [수정 2026-11-18] P2: 실기기 쪽 이름의 real_ 접두어를 뺌
        # (real_battery -> battery_from_topic)
        self.battery_from_topic = bool(battery_topic)
        self.follow_dist, self.resume_dist = p('follow_pause_dist', 0.30).value, p('follow_resume_dist', 0.22).value
        self.guest_timeout = p('guest_timeout', 20.0).value
        # [수정 2026-11-17] UR-03: 손님 동행 확인을 /frybot/guest_track
        # (AI 서버의 추적 결과)으로 받음. 예전에는 시뮬 전용
        # /sim/world_state 의 손님 좌표를 직접 읽어 실기기에서는 확인이 없었음.
        # guest_track_required: 추적 값이 한 번도 오지 않아도 이탈로 볼지
        # guest_track_stale: 이 시간(초)보다 오래된 값은 "놓침"으로 봄
        self.track_required = p('guest_track_required', False).value
        self.track_stale = p('guest_track_stale', 1.5).value
        self.track = None            # (visit_id, visible, distance, 수신 시각)
        self.guide_goal = None       # 진행 중인 안내 경로의 목표 핸들
        self.track_warned = False
        # [수정 2026-11-17] UR-03: 실측 지도에서도 안내 구간(입구 -> 테이블)을
        # Nav2 로 후진 주행. 실측 지도의 FollowPath 는 전진 전용이라 후진용
        # 제어기 FollowPathReverse 를 구간마다 고름(_nav2_segment).
        # false 면 실측 지도의 안내 구간을 전진으로 주행
        self.guide_reverse = p('guide_reverse', True).value
        self._controller = ''        # 마지막으로 고른 Nav2 제어기
        # [수정 2026-11-17] UR-21: 실기기의 충전 여부 판정
        # (_charging_from_battery, 2026-11-18 P2 에서 _real_charging 을 고침)
        self.charge_rise = p('charge_rise_pct', 1.0).value
        self.charge_window = p('charge_window_sec', 300.0).value
        self.idle_since, self.batt_hist = None, []
        # [수정 2026-11-18] T-39: 충전대(지도의 home_nodes) 근처에 서 있을 때만
        # 충전 여부를 판정. 충전대가 없는 실측 지도에서 배터리 값의 흔들림을
        # 충전으로 잘못 보아 CHARGING 을 보고했고, 관제가 이동 명령을 거절했음
        self.charger_radius = p('charger_radius', 0.10).value
        self.arm_task = ''
        # Central control liveness / emergency stop (/fms/heartbeat). 0 = drive without checking the heartbeat.
        self.fms_timeout = p('fms_timeout', 2.0).value
        self.hb_t, self.hb_session, self.estop, self.void = None, '', False, None
        self.nav2_retries = p('nav2_retries', 2).value       # measured map: extra tries of a segment Nav2 failed
        # Stepping aside (mode YIELD) on the real robot: back up along the granted edge with cmd_vel. The lidar looks
        # behind the robot first: scan angle of the robot's rear = pi - lidar_yaw (Pinky: lidar mounted turned by pi).
        self.yield_reverse = p('yield_reverse', True).value
        self.lidar_yaw = p('lidar_yaw', math.pi).value
        self.rear_stop = p('rear_stop_dist', 0.10).value     # m from the lidar (the rear edge is 4.5 cm behind it)
        self.rear, self.rear_t = None, 0.0                   # nearest return behind the robot, wall time of the scan
        self.rear_wanted = 0.0                               # scans are evaluated until this wall time
        self.node_id, self.drive_error = '', False
        g = Graph()
        self.measured_map = bool(g.map_id)
        self.home = g.nodes[g.home_of(self.rid)]
        # [수정 2026-11-18] T-39: 충전 판정에 쓰는 충전대 좌표(실측 지도는 없음)
        self.charger_xy = [g.nodes[n] for n in sorted(g.home_nodes)]
        self.x, self.y, self.yaw = self.home[0], self.home[1], 0.0
        self.spawn = (self.x, self.y)
        self.battery, self.charging = p('battery', 100.0).value, False
        self.cur, self.grants = None, {}
        self.pv, self.reached, self.task_id, self.nav_state = 0, -1, '', 'IDLE'
        self.arm_state, self.arm_q, self.wheel = 'IDLE', list(REST), 0.0
        self.lock = threading.Lock()
        cb = ReentrantCallbackGroup()
        self.pub_status = self.create_publisher(RobotStatus, '/fleet/robot_status', 50)
        self.pub_arm_js = self.create_publisher(JointState, f'/{self.rid}/arm/joint_states', 10)
        self.pub_cmd = self.create_publisher(Twist, f'/{self.rid}/cmd_vel', 10)
        self.create_subscription(TrafficGrant, '/fms/traffic_grant', self._grant, QOS, callback_group=cb)
        self.create_subscription(FleetHeartbeat, '/fms/heartbeat', self._heartbeat, 10, callback_group=cb)
        if self.drive != 'kinematic':
            self.create_subscription(LaserScan, f'/{self.rid}/scan', self._scan, qos_profile_sensor_data, callback_group=cb)
        self.create_subscription(GuestTrack, '/frybot/guest_track',
                                 self._guest_track, 10, callback_group=cb)
        # [수정 2026-11-17] UR-17, 19: 서빙 팔의 상태·오류 보고
        self.pub_arm_status = self.create_publisher(
            ArmStatus, '/fleet/arm_status', 20)
        self.n2 = dict(key=None, state='', handle=None, t_fail=0.0, fails=0, fail_key=None, turning=None, direct=None, try_fk=None,
                       try_t0=0.0, try_pos=(0.0, 0.0), goal_fk=None)
        # docks by node position; dk = state of the docking approach in progress
        self.docks = {(round(d['x'], 3), round(d['y'], 3)): d for d in docks().values()}
        self.use_docking = p('docking', True).value          # false: Nav2 segment + heading trim only
        self.yaw_tol = p('dock_yaw_tolerance', 0.012).value  # rad, heading error left after the trim
        self.trim_w = p('dock_trim_speed', 0.15).value       # rad/s, slowest turn of the trim (above the motor deadband)
        self.dk = dict(key=None, stage='', state='', handle=None, marker=-1)
        self.det = None                                      # (yaw of the dock in the odometry frame, wall time)
        if self.drive == 'nav2':
            self.dock_cli = ActionClient(self, DockRobot, f'/{self.rid}/dock_robot', callback_group=cb)
            self.pub_dock_target = self.create_publisher(Int32, f'/{self.rid}/dock_target', 5)
            self.create_subscription(PoseStamped, f'/{self.rid}/detected_dock_pose', self._detected, 5, callback_group=cb)
            self.create_timer(0.5, lambda: self.pub_dock_target.publish(Int32(data=self.dk['marker'])), callback_group=cb)
            self.nav2 = ActionClient(self, NavigateToPose, f'/{self.rid}/navigate_to_pose', callback_group=cb)
            self.pub_limit = self.create_publisher(SpeedLimit, f'/{self.rid}/speed_limit', 10)
            # [수정 2026-11-17] UR-03: 구간에 쓸 Nav2 제어기 선택
            # (bt_navigator 의 ControllerSelector 가 받음, 마지막 값 유지)
            self.pub_controller = self.create_publisher(
                String, f'/{self.rid}/controller_selector',
                QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.TRANSIENT_LOCAL))
            self._limit = None
            self.clear_local = self.create_client(ClearEntireCostmap, f'/{self.rid}/local_costmap/clear_entirely_local_costmap',
                                                  callback_group=cb)
        self.odom, self.have_truth = (0.0, 0.0, 0.0), False
        # [수정 2026-11-17] T-25: 실측 지도를 경량 시뮬(drive=kinematic)로
        # 돌리면 위치 추정원이 없어 상태 보고가 나가지 않았음. 자세를 직접
        # 움직이므로 그 값을 참값으로 봄. 실기기(drive=nav2)는 해당 없음
        if self.drive == 'kinematic' and self.measured_map:
            self.have_truth = True
        if self.pose_source == 'tf':
            self.tf_buf = Buffer()
            self.tf_listener = TransformListener(self.tf_buf, self)
            self.pub_init = self.create_publisher(PoseWithCovarianceStamped, f'/{self.rid}/initialpose', 1)
            self.create_timer(0.05, self._tf_pose, callback_group=cb)
            if not self.measured_map:
                self.create_timer(2.0, self._initial_pose, callback_group=cb)
        if self.battery_from_topic:
            # [수정 2026-11-17] UR-21: 충전 판정을 위해 값을 기록하며 받음
            self.create_subscription(Float32, battery_topic, self._battery, 5,
                                     callback_group=cb)
        if self.drive in ('cmd_vel', 'nav2'):
            self.create_subscription(Odometry, f'/{self.rid}/odom', self._odom, 20, callback_group=cb)
        ActionServer(self, NavigateRoute, f'/{self.rid}/navigate_route', execute_callback=self._navigate,
                     goal_callback=lambda g_: GoalResponse.ACCEPT, cancel_callback=lambda g_: CancelResponse.ACCEPT,
                     handle_accepted_callback=self._accepted, callback_group=cb)
        ActionServer(self, ArmJob, f'/{self.rid}/arm_job', execute_callback=self._arm_job,
                     cancel_callback=lambda g_: CancelResponse.ACCEPT, callback_group=cb)
        if self.drive == 'nav2':
            self.create_timer(1.0, self._refresh_costmap, callback_group=cb)
        self.cam = CameraStreamer(f'{self.rid}_front', host=p('ai_host', '127.0.0.1').value,
                                  port=p('ai_udp_port', 9100).value)
        self.create_timer(0.1, self._publish, callback_group=cb)
        self.create_timer(1.0, lambda: self.cam.send('amr', robot_id=self.rid, x=self.x, y=self.y), callback_group=cb)
        self.create_timer(0.5, self._publish_arm, callback_group=cb)
        # [수정 2026-11-18] P3(D6): 시뮬 전용 입력·출력(/gz/model_poses,
        # /sim/world_state, map -> base TF, 가짜 배터리·바퀴 관절값)은
        # 시뮬 값일 때만 붙는 sim_backend 가 맡음. 실기기(nav2/tf)는 없음
        self.sim = (SimBackend(self, cb, [g.nodes[n] for n in g.home_nodes])
                    if self.drive == 'kinematic' or self.pose_source != 'tf'
                    else None)
        self.get_logger().info(f'{self.rid} ready at ({self.x:.2f}, {self.y:.2f}) drive={self.drive}')

    # ------------------------------------------------------------ inputs
    def _grant(self, m):
        # Permissions are kept per plan version and only for the current route or a newer one: versions never repeat
        # (the Task Manager numbers them from a time-based start), so anything older is stale.
        if m.robot_id == self.rid and m.plan_version >= self.pv:
            self.grants[m.plan_version] = max(self.grants.get(m.plan_version, 0), m.granted_index)

    def _heartbeat(self, m):
        if self.hb_session and m.session != self.hb_session:      # the Task Manager restarted: it knows nothing of
            self.grants = {}                                       # our route and holds no locks for it
            self.void = self.cur
            self.get_logger().warn(f'{self.rid}: Task Manager restarted, dropping the current route and permissions')
        self.hb_session, self.hb_t = m.session, time.time()
        estop = self.rid in m.estop
        if estop != self.estop:
            self.get_logger().warn(f'{self.rid}: emergency stop {"ON" if estop else "released"}')
            if estop and self.drive != 'kinematic':
                self.pub_cmd.publish(Twist())
        self.estop = estop

    def _fms_alive(self):
        return self.fms_timeout <= 0 or (self.hb_t is not None and time.time() - self.hb_t <= self.fms_timeout)

    def _scan(self, m):
        """Nearest lidar return in the 50 deg sector behind the robot (for backing out of the way). Only evaluated
        while the robot is about to reverse or reversing: the scan arrives at 10 Hz and the Pinky's CPU is busy."""
        if time.time() > self.rear_wanted:
            return
        rear = math.pi - self.lidar_yaw
        best = float('inf')
        for i, r in enumerate(m.ranges):
            if 0.06 <= r < best and abs(wrap(m.angle_min + i * m.angle_increment - rear)) <= 0.44:
                best = r
        self.rear, self.rear_t = best, time.time()

    # [수정 2026-11-18] P3: _world(/sim/world_state)는 sim_backend 로 옮김

    # [수정 2026-11-17] 신규 (UR-03): 손님 추적
    def _guest_track(self, m: GuestTrack) -> None:
        """AI 서버가 본 손님의 동행 상태를 받는다 (이 로봇 것만)."""
        if m.robot_id == self.rid:
            self.track = (m.visit_id, m.visible, m.distance, time.time())

    # [수정 2026-11-18] P3: _guide_frame(안내 카메라 프레임 대역)은 sim_backend 로
    # 옮김. 실기기 카메라 영상 송신은 아직 없음

    def _guest_away(self, visit_id: int, limit: float) -> bool:
        """안내 중인 손님이 따라오지 못하고 있는지 판단한다.

        Args:
            visit_id: 안내 중인 손님 그룹.
            limit: 이 거리(m)보다 멀면 뒤처진 것으로 봄.

        Returns:
            멈춰서 기다려야 하면 True. 추적 값을 받은 적이 없으면
            guest_track_required 값(기본 False: 확인 없이 진행).
        """
        track = self.track
        if track is None or track[0] != visit_id:
            if not self.track_warned:
                self.track_warned = True
                self.get_logger().warn(
                    f'{self.rid}: no guest tracking for visit {visit_id} '
                    '(/frybot/guest_track): guiding without the follow check'
                    if not self.track_required else
                    f'{self.rid}: no guest tracking for visit {visit_id}: '
                    'waiting')
            return self.track_required
        _, visible, distance, stamp = track
        if time.time() - stamp > self.track_stale:
            return True                    # 추적이 끊김: 손님을 놓친 것으로 봄
        return not visible or distance > limit

    # [수정 2026-11-17] 신규 (UR-21): 실기기 충전 여부
    def _battery(self, m: Float32) -> None:
        """배터리 잔량(%)을 받고, 서 있는 동안의 값을 기록한다."""
        self.battery = float(m.data)
        now = time.time()
        if self.idle_since is not None and now - self.idle_since >= 30.0:
            self.batt_hist.append((now, self.battery))
            self.batt_hist = [s for s in self.batt_hist
                              if now - s[0] <= self.charge_window]

    # [수정 2026-11-18] P2: 이름에서 real_ 접두어를 뺌
    def _charging_from_battery(self) -> bool:
        """실기기가 충전 중인지 배터리 잔량의 변화로 추정한다.

        Pinky 는 충전 신호를 따로 내지 않는다. 30초 넘게 서 있는 동안
        잔량이 charge_window_sec 안에 charge_rise_pct 이상 올랐으면 충전 중으로
        본다 (정지 직후 전압이 회복되는 구간은 제외). 임계값은 실기기 확인 필요.
        """
        # [수정 2026-11-18] T-39: 충전대 근처가 아니면 충전 중이 아님
        on_charger = any(math.hypot(self.x - cx, self.y - cy)
                         < self.charger_radius for cx, cy in self.charger_xy)
        if (self.nav_state != 'IDLE' or self.arm_state != 'IDLE'
                or not on_charger):
            self.idle_since, self.batt_hist = None, []
            return False
        if self.idle_since is None:
            self.idle_since = time.time()
        if len(self.batt_hist) < 2:
            return False
        low = min(pct for _, pct in self.batt_hist)
        return self.batt_hist[-1][1] - low >= self.charge_rise

    # [수정 2026-11-17] 신규 (UR-17, 19): 서빙 팔 상태 보고
    def _publish_arm(self) -> None:
        """서빙 팔의 상태를 /fleet/arm_status 로 보낸다 (대역: 오류 없음)."""
        if self.measured_map and not self.have_truth:
            return
        busy = self.arm_state != 'IDLE'
        self.pub_arm_status.publish(ArmStatus(
            stamp=self.get_clock().now().to_msg(), arm_id=self.rid,
            state='ARM_OPERATING' if busy else 'IDLE',
            job=self.arm_state if busy else '',
            task_id=self.arm_task if busy else '', error=''))

    def _odom(self, m):
        p, q = m.pose.pose.position, m.pose.pose.orientation
        self.odom = (p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))
        if not self.have_truth and self.pose_source != 'tf':   # no localisation source: dead reckoning from the start
            self.x, self.y, self.yaw = self.spawn[0] + p.x, self.spawn[1] + p.y, self.odom[2]

    def _tf_pose(self):
        """Localisation on the real robot: map -> base_frame from TF (AMCL publishes map -> odom)."""
        # [수정 2026-11-17] D4: 변환의 시각을 확인. AMCL 이나 오도메트리가
        # 죽으면 최신 변환이 오래된 채 남는데, 전에는 그 굳은 위치를 계속
        # 쓰고 보고했음. except 도 TransformException 으로 좁힘
        try:
            tfm = self.tf_buf.lookup_transform('map', self.base_frame, Time())
        except TransformException:                 # not localised yet
            self.tf_ok = False
            return
        now = self.get_clock().now()
        stamp = Time.from_msg(tfm.header.stamp, clock_type=now.clock_type)
        if self.tf_stale > 0 and \
                (now - stamp).nanoseconds / 1e9 > self.tf_stale:
            self.tf_ok = False
            return
        t = tfm.transform
        q = t.rotation
        self.x, self.y = t.translation.x, t.translation.y
        self.yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.have_truth = self.tf_ok = True

    # [수정 2026-11-17] 신규 (D4): 위치 추정을 믿을 수 있는지
    def _loc_lost(self) -> bool:
        """TF 로 위치를 받는 로봇이 지금 위치를 모르는지 판단한다.

        Returns:
            pose_source 가 tf 이고, 위치를 아직 못 받았거나 최신 변환이
            tf_stale_sec 보다 오래됐으면 True. 그 밖(시뮬)에는 항상 False.
        """
        if self.pose_source != 'tf' or self.tf_stale <= 0:
            return False
        return not (self.have_truth and self.tf_ok)

    def _initial_pose(self):
        """Until AMCL answers, tell it where the robot was put down: on its home spot, facing +x (into the store)."""
        if self.have_truth:
            return
        m = PoseWithCovarianceStamped()
        m.header.frame_id, m.header.stamp = 'map', self.get_clock().now().to_msg()
        m.pose.pose.position.x, m.pose.pose.position.y = self.spawn
        m.pose.pose.orientation.w = 1.0
        m.pose.covariance[0] = m.pose.covariance[7] = 0.02 ** 2
        m.pose.covariance[35] = 0.1 ** 2
        self.pub_init.publish(m)

    # [수정 2026-11-18] P3: _gz_pose(Gazebo 참값 자세, map -> odom 보정)는
    # sim_backend 로 옮김

    # ------------------------------------------------------------ NavigateRoute (GuideGuest when mode == GUIDE)
    def _accepted(self, gh):
        with self.lock:
            self.cur = gh                 # a newer plan pre-empts the running one
        gh.execute()

    def _navigate(self, gh):
        goal = gh.request
        route, pv, guide = goal.route, goal.plan_version, goal.mode == 'GUIDE'
        yielding = goal.mode == 'YIELD'
        rev, back_streak, yield_rev = {}, True, None   # segment index -> drive in reverse
        self.pv, self.task_id = pv, goal.task_id
        self.grants = {k: v for k, v in self.grants.items() if k >= pv}      # drop permissions of older routes
        res = NavigateRoute.Result(plan_version=pv)
        reached = 0 if route and math.hypot(route[0].x - self.x, route[0].y - self.y) < 0.012 else -1
        self.reached = reached
        if reached == 0:
            self.node_id = route[0].node_id
        self._fb(gh, pv, reached, 'ACCEPTED')
        # [수정 2026-11-17] UR-03: 안내 경로면 카메라 프레임을 보내기 시작
        if guide:
            self.guide_goal, self.track_warned = gh, False
        dt, lost_since = 0.05, None
        tries, rear_since = {}, None     # failed Nav2 attempts per segment / since when the way back is blocked
        pockets = set()                  # segments into a side spot that the route leaves again the way it came
        while rclpy.ok():
            if gh is self.cur and not gh.is_cancel_requested and (self.estop or gh is self.void):
                # emergency-stop channel, or the Task Manager restarted: stop here and give the route back
                self._stop()
                if self.drive != 'kinematic':
                    self.pub_cmd.publish(Twist())
                res.reached_index, res.reason = reached, 'E_STOP' if self.estop else 'FMS_RESTART'
                self.nav_state = 'IDLE'
                gh.abort()
                return res
            if gh is not self.cur or gh.is_cancel_requested:
                self._stop()
                res.reached_index, res.reason = reached, 'CANCELED' if gh.is_cancel_requested else 'PREEMPTED'
                if gh.is_cancel_requested:
                    gh.canceled()
                    self.nav_state = 'IDLE'
                else:
                    gh.abort()
                return res
            # [수정 2026-11-17] D4: 위치를 모르면 움직이지 않음(Nav2 목표와
            # 직접 주행 모두 정지). 도착 판정보다 먼저 봄
            if self._loc_lost():
                self._stop()
                self.nav_state = 'WAIT_LOC'
                time.sleep(dt)
                continue
            if reached >= len(route) - 1:
                break
            tgt = reached + 1
            if not self._fms_alive():                             # central control silent: do not move on our own
                self._stop()
                if self.drive != 'kinematic':
                    self.pub_cmd.publish(Twist())
                self.nav_state = 'WAIT_FMS'
                time.sleep(dt)
                continue
            if tgt > 0 and tgt > self.grants.get(pv, 0):          # wait for the traffic permission
                self._stop()
                self.nav_state = 'WAIT_GRANT'
                time.sleep(dt)
                continue
            # [수정 2026-11-17] UR-03: 동행 확인을 추적 토픽 기준으로 바꿈
            # (_guest_away). 멈춤·재출발 거리와 시간 초과는 그대로
            if guide and tgt > 0:
                limit = self.resume_dist if self.nav_state == 'PAUSED_GUEST' else self.follow_dist
                if self._guest_away(goal.visit_id, limit):        # SR-007: guest fell behind -> stop and wait
                    self._stop()
                    if self.nav_state != 'PAUSED_GUEST':
                        self.nav_state, lost_since = 'PAUSED_GUEST', time.time()
                        self._fb(gh, pv, reached, 'PAUSED_GUEST')
                    if time.time() - lost_since > self.guest_timeout:    # SR-008
                        res.reached_index, res.reason = reached, 'GUEST_LOST'
                        self.nav_state = 'IDLE'
                        gh.abort()
                        return res
                    time.sleep(dt)
                    continue
            if tgt not in rev:
                # GUIDE: back up the whole guided leg, facing the guests.  YIELD: back out of the way into the side
                # spot.  NORMAL: when a new plan starts by going back the way we came (paths crossed), back up those
                # first segments instead of turning round in the one-robot-wide aisle.
                err = abs(wrap(math.atan2(route[tgt].y - self.y, route[tgt].x - self.x) - self.yaw))
                if math.hypot(route[tgt].x - self.x, route[tgt].y - self.y) < 0.05:
                    rev[tgt] = err > math.pi / 2          # settling onto a node a few cm away: never turn round for it
                elif guide and tgt > 0:
                    rev[tgt] = True
                elif yielding:
                    if yield_rev is None:                 # the first real segment decides: back out if the spot is behind
                        yield_rev = err > math.pi / 2
                    rev[tgt] = yield_rev
                else:
                    # A side spot the route leaves again the way it came (the planner lets another robot pass
                    # there): back into it, so the robot drives out forwards without turning round twice.
                    if 0 < tgt < len(route) - 1 and route[tgt + 1].node_id == route[tgt - 1].node_id:
                        pockets.add(tgt)
                    rev[tgt] = tgt in pockets or (back_streak and tgt <= 2 and err > 2.1)
                    back_streak = rev[tgt]
            self.nav_state = 'MOVING'
            dock = None
            if tgt > 0 and tgt == len(route) - 1 and not guide and not yielding:     # the route ends on a dock
                dock = self.docks.get((round(route[tgt].x, 3), round(route[tgt].y, 3)))
            if dock is not None:
                if self.drive == 'nav2':
                    self._set_speed_limit(None)
                done = self._dock_segment((pv, tgt), dock, rev[tgt], dt, route[tgt - 1])
            elif self.drive == 'nav2' and self.measured_map and rev[tgt] and self.yield_reverse \
                    and (yielding or tgt in pockets):
                # Real robot stepping aside: back up along the granted edge (the Nav2 controller of the measured map
                # does not reverse). The lidar must show the way back clear; if it stays blocked, turn round instead.
                if self._rear_blocked():
                    self.pub_cmd.publish(Twist())
                    self.nav_state = 'YIELD_BLOCKED'
                    rear_since = rear_since or time.time()
                    if time.time() - rear_since > 6.0:
                        self.get_logger().warn(f'{self.rid}: way back to {route[tgt].node_id} is blocked, turning round')
                        rev[tgt], yield_rev, rear_since = False, False, None
                        pockets.discard(tgt)
                    done = False
                else:
                    rear_since, self.nav_state = None, 'YIELD'
                    done = self._step_toward(route[tgt].x, route[tgt].y, True, dt, min(self.speed, self.guide_speed))
                    if done:
                        self.pub_cmd.publish(Twist())
            elif self.drive == 'nav2':
                self._set_speed_limit(self.guide_speed if guide and tgt > 0 else None)
                # [수정 2026-11-17] UR-03: 실측 지도에서도 안내 구간은 Nav2 로
                # 후진(후진용 제어기). 그 밖의 후진은 전처럼 실측 지도에서 전진
                done = self._nav2_segment(
                    (pv, tgt), route[tgt].x, route[tgt].y,
                    rev[tgt] and (not self.measured_map or (
                        guide and tgt > 0 and self.guide_reverse)))
                if self.measured_map and self.n2['state'] == 'FAILED':
                    # Nav2 could not drive this segment (15 s without progress, or the goal failed). The FAILED mark
                    # must not outlive the attempt: it used to stay set, and every later route failed at once.
                    self._stop()
                    self.n2.update(key=None, state='', handle=None, try_fk=None, fails=0, fail_key=None)
                    tries[tgt] = tries.get(tgt, 0) + 1
                    if tries[tgt] <= self.nav2_retries:
                        self.get_logger().warn(f'{self.rid}: Nav2 failed the segment to {route[tgt].node_id}, '
                                               f'retry {tries[tgt]}/{self.nav2_retries}')
                        if self.clear_local.service_is_ready():
                            self.clear_local.call_async(ClearEntireCostmap.Request())
                        self.nav_state = 'NAV2_RETRY'
                        time.sleep(1.0)
                        continue
                    self.nav_state, self.drive_error = 'IDLE', True
                    res.reached_index, res.reason = reached, 'NAV2_FAILED'
                    gh.abort()
                    return res
            else:
                done = self._step_toward(route[tgt].x, route[tgt].y, rev[tgt], dt,
                                         self.guide_speed if guide and tgt > 0 else self.speed)
            if done:
                reached = self.reached = tgt
                self.node_id, self.drive_error = route[tgt].node_id, False
                self._fb(gh, pv, reached, 'MOVING')
            time.sleep(dt)
        self._stop()
        if self.drive == 'nav2':
            self._set_speed_limit(None)
        self.nav_state = 'IDLE'
        res.success, res.reached_index, res.reason = True, reached, 'OK'
        gh.succeed()
        return res

    def _fb(self, gh, pv, reached, state):
        gh.publish_feedback(NavigateRoute.Feedback(plan_version=pv, reached_index=reached, state=state))

    def _step_toward(self, tx, ty, reverse, dt, v=None):
        """Navigator: turn in place, then drive straight. reverse=True drives backwards (rear toward the target)."""
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        v = self.speed if v is None else v
        tol = 0.004 if self.drive == 'kinematic' else 0.015
        if d <= max(tol, v * dt if self.drive == 'kinematic' else 0):
            if self.drive == 'kinematic':
                self.x, self.y = tx, ty
            return True
        want = wrap(math.atan2(dy, dx) + (math.pi if reverse else 0.0))
        err = wrap(want - self.yaw)
        if self.drive == 'kinematic':
            if abs(err) > 0.05:
                self.yaw = wrap(self.yaw + max(-self.turn_rate * dt, min(self.turn_rate * dt, err)))
            else:
                self.yaw = want
                self.x += dx / d * v * dt
                self.y += dy / d * v * dt
                self.wheel += (-1 if reverse else 1) * v * dt / 0.028
                self.battery = max(0.0, self.battery - 0.02 * dt)
        else:
            cmd = Twist()
            if abs(err) > 0.2:
                cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
            else:
                cmd.linear.x = (-v if reverse else v) * min(1.0, d / 0.03 + 0.3)
                cmd.angular.z = 2.0 * err
            self.pub_cmd.publish(cmd)
        return False

    def _rear_blocked(self):
        """True when the lidar shows something close behind the robot, or gives no fresh scan to judge by."""
        if self.rear_stop <= 0:
            return False
        self.rear_wanted = time.time() + 2.0
        return self.rear is None or time.time() - self.rear_t > 1.0 or self.rear < self.rear_stop

    def _stop(self):
        # [수정 2026-11-17] R1-1/T-22: 직접 주행(양보 후진, 도킹 creep) 중
        # 취소·선점되면 마지막 cmd_vel이 남아 계속 움직였음.
        # 정지할 때 항상 0 속도를 한 번 보냄
        if self.drive != 'kinematic':
            self.pub_cmd.publish(Twist())
        self._dock_cancel()
        if self.drive == 'cmd_vel':
            self.pub_cmd.publish(Twist())
        elif self.drive == 'nav2':
            self._nav2_cancel()

    # ------------------------------------------------------------ precise docking
    def _detected(self, m):
        q = m.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        # the same pose in the map frame (through the robot's pose in both frames), to compare it with the layout
        ox, oy, oyaw = self.odom
        dx, dy = m.pose.position.x - ox, m.pose.position.y - oy
        bx, by = math.cos(oyaw) * dx + math.sin(oyaw) * dy, -math.sin(oyaw) * dx + math.cos(oyaw) * dy
        self.det = (yaw, time.time(), self.x + math.cos(self.yaw) * bx - math.sin(self.yaw) * by,
                    self.y + math.sin(self.yaw) * bx + math.cos(self.yaw) * by)

    def _dock_segment(self, key, d, reverse, dt, prev):
        """Last segment of a route that ends on dock `d`. Returns True once the robot stands on the dock pose.
        start -> turn (to the dock heading) -> docking (Nav2 docking server) -> trim (heading), or, when the dock is
        not straight ahead of the node the robot comes from or docking fails, drive (ordinary segment) -> trim."""
        k = self.dk
        fk = (round(d['x'], 3), round(d['y'], 3))
        if k['key'] != fk:
            k.update(key=fk, stage='start', state='', handle=None, marker=d.get('marker_id', -1), lat0=None, creep_t=None, still_t=None)
            self.det = None
            if self.drive == 'nav2':
                self.pub_dock_target.publish(Int32(data=k['marker']))
        c, s_ = math.cos(d['yaw']), math.sin(d['yaw'])
        along = (d['x'] - self.x) * c + (d['y'] - self.y) * s_          # distance still to go along the dock heading
        lat = -(d['x'] - self.x) * s_ + (d['y'] - self.y) * c
        if k['stage'] == 'start':
            # Nav2 ends a segment up to 1.5 cm before the node; for a dock entered from the side that is a sideways
            # offset the short approach cannot remove. Creep onto the node before the dock first.
            if self._creep(prev.x, prev.y, k):
                return False
            ok = (self.drive == 'nav2' and self.use_docking and 0.03 <= along <= 0.30 and abs(lat) <= 0.03
                  and self.dock_cli.server_is_ready())
            k['stage'] = 'turn' if ok else 'drive'
        if k['stage'] == 'turn':
            self.nav_state = 'TURN'
            if self._rotate(wrap(d['yaw'] - self.yaw), 0.08, dt, 0.4):
                return False
            if not self.measured_map and self.clear_local.service_is_ready():
                self.clear_local.call_async(ClearEntireCostmap.Request())
            g = DockRobot.Goal()
            g.use_dock_id, g.navigate_to_staging_pose = False, False
            g.dock_type = 'marker_dock' if d['kind'] == 'marker' else 'pose_dock'
            g.dock_pose.header.frame_id, g.dock_pose.header.stamp = 'map', self.get_clock().now().to_msg()
            g.dock_pose.pose.position.x, g.dock_pose.pose.position.y = float(d['x']), float(d['y'])
            g.dock_pose.pose.orientation.z, g.dock_pose.pose.orientation.w = math.sin(d['yaw'] / 2), math.cos(d['yaw'] / 2)
            k.update(stage='docking', state='ACTIVE', handle=None, lat0=lat)
            self.dock_cli.send_goal_async(g).add_done_callback(lambda f, fk=fk: self._dock_accepted(f, fk))
            return False
        if k['stage'] == 'docking':
            self.nav_state = 'DOCKING'
            if k['state'] == 'SUCCEEDED':
                k['stage'] = 'trim'
            elif k['state'] == 'ACTIVE' and k['handle'] is not None and along <= 0.006 and abs(lat) < 0.03:
                # Level with the dock pose. The server only stops within docking_threshold of the pose itself, which
                # a robot a few mm to the side never reaches: it would drive on into the wall.
                k['handle'].cancel_goal_async()
                self.pub_cmd.publish(Twist())
                k.update(stage='trim', state='', handle=None)
            elif k['state'] == 'FAILED' or along < -0.02:               # failed, or drove past the dock pose
                self.get_logger().warn(f'{self.rid}: docking at {d["name"]} did not finish '
                                       f'({k["state"] or "overshoot"}), finishing the segment with Nav2')
                if k['handle'] is not None and k['state'] == 'ACTIVE':
                    k['handle'].cancel_goal_async()
                self.pub_cmd.publish(Twist())
                k.update(stage='drive', state='', handle=None)
            return False
        if k['stage'] == 'drive':
            if self.drive == 'nav2':
                done = self._nav2_segment(key, d['x'], d['y'], reverse)
            else:
                done = self._step_toward(d['x'], d['y'], reverse, dt)
            if not done:
                return False
            k.update(stage='settle', creep_t=None)
        if k['stage'] == 'settle':                                      # same creep, onto the dock node itself
            if self._creep(d['x'], d['y'], k):
                return False
            k['stage'] = 'trim'
        # trim: turn in place to the dock heading. With a marker in view the error comes from the marker (dock heading
        # and robot heading both in the odometry frame), otherwise from the localisation.
        self.nav_state = 'DOCKING'
        err = wrap(d['yaw'] - self.yaw)
        if d['kind'] == 'marker' and self.det is not None and time.time() - self.det[1] < 1.0:
            err = wrap(self.det[0] - self.odom[2])
        if self._rotate(err, self.yaw_tol, dt, self.trim_w):
            k['still_t'] = None
            return False
        if k.get('still_t') is None:                 # stand still for a moment and check again (coasting, a fresh
            k['still_t'] = time.time()               # marker reading taken at rest)
        if time.time() - k['still_t'] < 0.5:
            return False
        note = ''
        if d['kind'] == 'marker':
            note = (', marker not seen' if self.det is None else
                    f', marker puts the dock {(self.det[2] - d["x"]) * 1000:+.0f} / {(self.det[3] - d["y"]) * 1000:+.0f} mm '
                    f'(x / y) from its map position')
        self.get_logger().info(f'{self.rid}: docked at {d["name"]} ({self.x:.3f}, {self.y:.3f}, '
                               f'{math.degrees(self.yaw):.1f} deg): {along * 1000:+.0f} mm short, {lat * 1000:+.0f} mm '
                               f'sideways, heading error {math.degrees(wrap(d["yaw"] - self.yaw)):.1f} deg' + note +
                               (f', approach started {k["lat0"] * 1000:+.0f} mm sideways' if k.get('lat0') is not None else ''))
        k.update(key=None, stage='', state='', handle=None, marker=-1, lat0=None)
        if self.drive == 'nav2':
            self.pub_dock_target.publish(Int32(data=-1))
        return True

    def _creep(self, tx, ty, k):
        """Drive straight (no turning) until the point (tx, ty) is level with the robot; only for the last 3 cm that
        the Nav2 goal tolerance leaves. Returns True while moving."""
        if self.drive == 'kinematic':
            return False
        f = (tx - self.x) * math.cos(self.yaw) + (ty - self.y) * math.sin(self.yaw)
        if k.get('creep_t') is None:
            k['creep_t'] = time.time()
        if 0.003 < abs(f) <= 0.03 and time.time() - k['creep_t'] < 4.0:
            self.nav_state = 'DOCKING'
            cmd = Twist()
            cmd.linear.x = math.copysign(0.02, f)
            self.pub_cmd.publish(cmd)
            return True
        self.pub_cmd.publish(Twist())
        k['creep_t'] = None
        return False

    def _rotate(self, err, tol, dt, w_min):
        """Turn in place by `err`. Returns True while still turning, False (and stops) once within `tol`."""
        if abs(err) <= tol:
            if self.drive != 'kinematic':
                self.pub_cmd.publish(Twist())
            return False
        if self.drive == 'kinematic':
            self.yaw = wrap(self.yaw + max(-self.turn_rate * dt, min(self.turn_rate * dt, err)))
        else:
            cmd = Twist()
            cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
            if abs(cmd.angular.z) < w_min:
                cmd.angular.z = math.copysign(w_min, err)
            self.pub_cmd.publish(cmd)
        return True

    def _dock_accepted(self, fut, fk):
        gh, k = fut.result(), self.dk
        if k['key'] != fk or k['stage'] != 'docking':
            if gh.accepted:
                gh.cancel_goal_async()
            return
        if not gh.accepted:
            k['state'] = 'FAILED'
            return
        k['handle'] = gh
        gh.get_result_async().add_done_callback(lambda f, fk=fk: self._dock_result(f, fk))

    def _dock_result(self, fut, fk):
        k = self.dk
        if k['key'] == fk and k['stage'] == 'docking':
            r = fut.result()
            k['state'] = 'SUCCEEDED' if r.status == 4 and r.result.success else 'FAILED'

    def _dock_cancel(self):
        k = self.dk
        if k['key'] is None:
            return
        if k['stage'] == 'docking' and k['handle'] is not None:
            k['handle'].cancel_goal_async()
        if k['stage'] in ('turn', 'docking', 'trim') and self.drive != 'kinematic':
            self.pub_cmd.publish(Twist())
        k.update(key=None, stage='', state='', handle=None, marker=-1)

    # ------------------------------------------------------------ Nav2 segment driving
    def _set_speed_limit(self, v):
        """Guiding is slower than normal driving: cap the Nav2 controller through its speed-limit topic."""
        if v != self._limit:
            self._limit = v
            m = SpeedLimit()
            m.header.stamp = self.get_clock().now().to_msg()
            m.percentage, m.speed_limit = False, float(v or 0.0)      # 0 = no limit
            self.pub_limit.publish(m)

    def _nav2_segment(self, key, tx, ty, reverse=False):
        """Drive to one granted roadmap node with Nav2. Returns True once the node is reached.
        reverse=True: turn the rear toward the node, then let the controller (allow_reversing) back up to it."""
        n = self.n2
        # Progress watch per target node (not per plan version: the Task Manager may re-send the same segment under
        # a new version every few seconds, which used to reset the failure count so the fallback never triggered).
        fk, now = (round(tx, 3), round(ty, 3)), time.time()
        if n.get('try_fk') != fk or math.hypot(self.x - n['try_pos'][0], self.y - n['try_pos'][1]) > 0.02:
            if n.get('try_fk') != fk and n.get('direct') != fk:
                n['direct'] = None
            n.update(try_fk=fk, try_t0=now, try_pos=(self.x, self.y))
        elif now - n['try_t0'] > 15.0 and n.get('direct') != fk:
            if self.measured_map:
                self._nav2_cancel()
                n['state'] = 'FAILED'
                return False
            self.get_logger().warn(f'{self.rid}: no progress toward {fk} for 15 s under Nav2, driving it directly')
            self._nav2_cancel()
            n.update(direct=fk, fails=0)
        if n.get('direct') == fk:                                   # Nav2 gave up on this segment: drive it directly
            v = self.guide_speed if self._limit else self.speed
            if self._step_toward(tx, ty, reverse, 0.05, v):
                self.pub_cmd.publish(Twist())
                n.update(key=None, state='', fails=0, direct=None, try_fk=None)
                return True
            return False
        if self.measured_map and n['state'] == 'FAILED':
            return False
        if n['key'] != key:
            # Turn toward the node before handing the segment to Nav2. Turning in place inside the controller makes
            # the footprint corners sweep cells marked by the lidar (aisle walls, a robot on the neighbouring node),
            # so RPP reports "collision ahead" and never finishes a U-turn after a replan sends the robot back.
            d = math.hypot(tx - self.x, ty - self.y)
            err = wrap(math.atan2(ty - self.y, tx - self.x) + (math.pi if reverse else 0.0) - self.yaw)
            # [수정 2026-11-17] UR-03: 실측 지도의 후진 구간도 여기서 뒤를
            # 목표로 돌림 (후진용 제어기에는 제자리 회전이 없음)
            if (not self.measured_map or reverse) and d > 0.05 \
                    and abs(err) > (0.15 if n.get('turning') == key else 0.5):
                n['turning'] = key
                self.nav_state = 'TURN'
                cmd = Twist()
                cmd.angular.z = max(-1.5, min(1.5, 2.5 * err))
                if abs(cmd.angular.z) < 0.4:
                    cmd.angular.z = math.copysign(0.4, err)
                self.pub_cmd.publish(cmd)
                return False
            if n.get('turning') == key:
                n['turning'] = None
                self.pub_cmd.publish(Twist())
            if not self.measured_map and n['fails'] >= 3 and n.get('fail_key') == fk:
                self.get_logger().warn(f'{self.rid}: Nav2 failed segment to {fk} {n["fails"]} times, driving it directly')
                n.update(direct=fk, state='', fails=0)
                return False
            if not self.nav2.server_is_ready():
                self.nav_state = 'WAIT_NAV2'
                return False
            if n['state'] == 'FAILED' and time.time() - n['t_fail'] < 1.0:
                return False
            # [수정 2026-11-17] UR-03: 이 구간에 쓸 제어기를 먼저 알림. 바뀌었을
            # 때는 한 주기 뒤에 목표를 보내 선택이 먼저 도착하게 함
            want = 'FollowPathReverse' if reverse else 'FollowPath'
            if want != self._controller:
                self._controller = want
                self.pub_controller.publish(String(data=want))
                return False
            # The simulated lidar sometimes returns only invalid ranges; marks from earlier scans would then never
            # be ray-traced away. Start every segment from an empty local costmap that the next scans refill.
            if self.clear_local.service_is_ready():
                self.clear_local.call_async(ClearEntireCostmap.Request())
            g = NavigateToPose.Goal()
            g.pose.header.frame_id = 'map'
            g.pose.header.stamp = self.get_clock().now().to_msg()
            g.pose.pose.position.x, g.pose.pose.position.y = float(tx), float(ty)
            yaw = math.atan2(ty - self.y, tx - self.x) + (math.pi if reverse else 0.0)
            g.pose.pose.orientation.z, g.pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            n.update(key=key, state='ACTIVE', handle=None, goal_fk=fk)
            self.nav2.send_goal_async(g).add_done_callback(lambda f, key=key: self._nav2_accepted(f, key))
            return False
        if n['state'] == 'SUCCEEDED':
            n.update(key=None, state='', fails=0, fail_key=None, try_fk=None)
            return True
        if n['state'] == 'FAILED':
            if math.hypot(tx - self.x, ty - self.y) < 0.03:       # close enough: count the node as reached
                n.update(key=None, state='', fails=0, fail_key=None, try_fk=None)
                return True
            n['fail_key'] = fk
            n['key'] = None                                         # blocked (obstacle in the costmap): try again
            self.nav_state = 'NAV2_RETRY'
        return False

    def _refresh_costmap(self):
        """While driving, rebuild the local costmap from the newest scan once a second (see _nav2_segment)."""
        if not self.measured_map and self.n2['key'] is not None and self.clear_local.service_is_ready():
            self.clear_local.call_async(ClearEntireCostmap.Request())

    def _nav2_accepted(self, fut, key):
        gh, n = fut.result(), self.n2
        if n['key'] != key:
            if gh.accepted:
                gh.cancel_goal_async()
            return
        if not gh.accepted:
            n.update(state='FAILED', t_fail=time.time())
            return
        n['handle'] = gh
        gh.get_result_async().add_done_callback(lambda f, key=key: self._nav2_result(f, key))

    def _nav2_result(self, fut, key):
        n = self.n2
        if n['key'] != key:
            return
        if fut.result().status == 4:                                # GoalStatus.STATUS_SUCCEEDED
            n['state'] = 'SUCCEEDED'
        else:
            fails = n['fails'] + 1 if n.get('fail_key') in (None, n.get('goal_fk')) else 1
            n.update(state='FAILED', t_fail=time.time(), fails=fails)

    def _nav2_cancel(self):
        n = self.n2
        if n.get('turning') is not None or n.get('direct') is not None:
            self.pub_cmd.publish(Twist())
            n['turning'] = None            # 'direct' stays: it belongs to the target node, not to this plan version
        if n['key'] is not None:
            if n['handle'] is not None:
                n['handle'].cancel_goal_async()
            n.update(key=None, state='', handle=None)

    # ------------------------------------------------------------ Arm Controller (serving arm on the AMR)
    def _arm_job(self, gh):
        g = gh.request
        self.arm_state, self.arm_task = g.job, g.task_id
        t0, dur = time.time(), max(0.2, g.duration)
        while rclpy.ok():
            if gh.is_cancel_requested or self.estop:      # canceled by the Task Manager, or emergency stop
                self.arm_q, self.arm_state = list(REST), 'IDLE'
                if gh.is_cancel_requested:
                    gh.canceled()
                else:
                    gh.abort()
                return ArmJob.Result(success=False, reason='CANCELED' if gh.is_cancel_requested else 'E_STOP')
            pr = (time.time() - t0) / dur
            if pr >= 1.0:
                break
            self.arm_q = arm_pose(g.job, pr, time.time())
            gh.publish_feedback(ArmJob.Feedback(phase=g.job, progress=float(pr)))
            time.sleep(0.05)
        self.arm_q, self.arm_state = list(REST), 'IDLE'
        gh.succeed()
        return ArmJob.Result(success=True, reason='OK')

    # ------------------------------------------------------------ status / TF
    def _publish(self):
        if self.measured_map and not self.have_truth:
            return
        now = self.get_clock().now().to_msg()
        if self.battery_from_topic:
            # [수정 2026-11-17] UR-21: 실기기는 충전대 좌표가 아니라 측정한
            # 잔량의 변화로 충전 여부를 판단 (예전에는 홈 노드에 서 있기만
            # 해도 충전 중으로 보고)
            self.charging = self._charging_from_battery()
        # [수정 2026-11-18] P3: 가짜 배터리·충전대 좌표 판정은 sim_backend
        elif self.sim is not None:
            self.sim.update_battery()
        state = 'CHARGING' if self.charging else (self.arm_state if self.arm_state != 'IDLE' else self.nav_state)
        error = ''
        if self.estop:
            state, error = 'E_STOP', 'EMERGENCY_STOP'
        elif self.nav_state == 'WAIT_FMS':
            error = 'COMMUNICATION_ERROR'
        # [수정 2026-11-17] D4: 위치 추정이 끊김(굳은 위치를 보고 중)
        elif self._loc_lost():
            error = 'SENSOR_ERROR'
        elif self.drive_error:
            error = 'DRIVE_ERROR'
        self.pub_status.publish(RobotStatus(stamp=now, robot_id=self.rid, state=state, x=self.x, y=self.y, yaw=self.yaw,
                                            battery=float(self.battery), charging=self.charging, task_id=self.task_id,
                                            plan_version=self.pv, reached_index=self.reached, node_id=self.node_id,
                                            arm_state=self.arm_state, error=error))
        # [수정 2026-11-18] P3(R1-4): map -> base TF(Nav2 없는 주행)와 가짜 바퀴
        # 관절값은 시뮬만 냄. 실기기의 바퀴 관절값은 pinky_driver 의 것만 남음.
        # With Nav2 the pose comes from map -> odom -> base: AMCL on the robot
        if self.sim is not None:
            self.sim.publish(now)
        aj = JointState()
        aj.header.stamp, aj.name, aj.position = now, JOINTS, [float(v) for v in self.arm_q]
        self.pub_arm_js.publish(aj)


def main():
    rclpy.init()
    n = MobileController()
    ex = MultiThreadedExecutor(num_threads=6)
    ex.add_node(n)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
