"""Expose separate robot odometry frames in one read-only RViz view."""
import rclpy
from geometry_msgs.msg import Point
from geometry_msgs.msg import PolygonStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
# [수정 2026-11-19] SIGINT·SIGTERM 으로 끝낼 때 나는 예외를 잡는 데 씀
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from tf2_msgs.msg import TFMessage
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
from visualization_msgs.msg import Marker, MarkerArray

# [수정 2026-11-19] 로드맵(roadmap.json)의 노드와 통로를 RViz 에 그리는 데 씀
from frybot_control.layout import Graph
from frybot_control.map_catalog import active_map_id
from frybot_control.map_catalog import profile
from frybot_interfaces.msg import RobotStatus

# [수정 2026-11-19] 로드맵 표시의 크기(m)와 색(r, g, b)
ROADMAP_Z = 0.01
NODE_SIZE = 0.03
EDGE_WIDTH = 0.006
NAME_HEIGHT = 0.03
EDGE_COLOR = (0.25, 0.45, 0.85)
NODE_COLOR = (0.10, 0.30, 0.80)
HOME_COLOR = (0.95, 0.45, 0.05)
NAME_COLOR = (0.10, 0.10, 0.10)


# [수정 2026-11-19] 신규: 로드맵을 RViz 마커로 바꿈
def roadmap_markers(graph: Graph, homes: list) -> tuple:
    """로드맵의 통로·노드 마커와 노드 이름 마커를 만든다.

    Args:
        graph: 지도의 로드맵.
        homes: 출발 노드 이름 목록 (다른 색으로 그림).

    Returns:
        (통로와 노드의 MarkerArray, 노드 이름의 MarkerArray).
    """
    def base(ns: str, mid: int, kind: int, color: tuple) -> Marker:
        marker = Marker()
        marker.header.frame_id = 'map'
        marker.ns, marker.id, marker.type = ns, mid, kind
        marker.pose.orientation.w = 1.0
        marker.color.r, marker.color.g, marker.color.b = color
        marker.color.a = 1.0
        return marker

    def point(name: str) -> Point:
        x, y = graph.nodes[name]
        return Point(x=float(x), y=float(y), z=ROADMAP_Z)

    edges = base('roadmap_edges', 0, Marker.LINE_LIST, EDGE_COLOR)
    edges.scale.x = EDGE_WIDTH
    for a, b in graph.edges:
        edges.points += [point(a), point(b)]
    nodes = base('roadmap_nodes', 0, Marker.SPHERE_LIST, NODE_COLOR)
    start = base('roadmap_homes', 0, Marker.SPHERE_LIST, HOME_COLOR)
    for marker, scale in ((nodes, NODE_SIZE), (start, NODE_SIZE * 1.4)):
        marker.scale.x = marker.scale.y = scale
        marker.scale.z = 0.004
    names = []
    for index, name in enumerate(sorted(graph.nodes)):
        (start if name in homes else nodes).points.append(point(name))
        label = base('roadmap_names', index, Marker.TEXT_VIEW_FACING,
                     NAME_COLOR)
        label.pose.position = point(name)
        label.pose.position.y += NODE_SIZE
        label.scale.z = NAME_HEIGHT
        label.text = name
        names.append(label)
    shapes = [m for m in (edges, nodes, start) if m.points]
    return MarkerArray(markers=shapes), MarkerArray(markers=names)


class FleetRviz(Node):
    def __init__(self):
        super().__init__('fleet_rviz')
        robots = self.declare_parameter('robot_ids', ['pinky1', 'pinky2']).value
        palette = [(0.05, 0.65, 0.35), (0.9, 0.35, 0.13), (0.58, 0.2, 0.92), (0.01, 0.52, 0.78)]
        self.colors = {rid: palette[i % len(palette)] for i, rid in enumerate(robots)}
        self.tf = TransformBroadcaster(self)
        self.tf_static = StaticTransformBroadcaster(self)
        self.markers = self.create_publisher(MarkerArray, '/fleet_rviz/robots', 10)
        self.create_subscription(RobotStatus, '/fleet/robot_status', self.robot, 10)
        map_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        # [수정 2026-11-19] 로드맵의 노드·통로와 노드 이름을 한 번 내보냄
        # (늦게 뜬 RViz 도 받도록 latched). 지도는 map_id 파라미터, 없으면
        # 환경 변수 FRYBOT_MAP_ID. 둘 다 없으면 그리지 않음
        map_id = self.declare_parameter('map_id', '').value or active_map_id()
        if map_id:
            self.pub_roadmap = self.create_publisher(
                MarkerArray, '/fleet_rviz/roadmap', map_qos)
            self.pub_names = self.create_publisher(
                MarkerArray, '/fleet_rviz/roadmap_names', map_qos)
            try:
                graph = Graph(map_id)
                # 출발 노드 전부(런치에 없는 로봇의 것도)를 다른 색으로
                homes = list(profile(map_id).get('homes', ()))
            except (ValueError, OSError) as err:
                self.get_logger().warning(f'로드맵을 그리지 못함: {err}')
            else:
                shapes, names = roadmap_markers(graph, homes)
                self.pub_roadmap.publish(shapes)
                self.pub_names.publish(names)
                self.get_logger().info(
                    f'로드맵 {map_id}: 노드 {len(graph.nodes)}개, '
                    f'통로 {len(graph.edges)}개')
        self.local_maps = {}
        self.footprints = {}
        for rid in robots:
            prefix = f'/fleet_rviz/{rid}'
            nav = f'/{rid}/local_costmap'
            self.local_maps[rid] = self.create_publisher(OccupancyGrid, f'{prefix}/local_costmap', map_qos)
            self.footprints[rid] = self.create_publisher(PolygonStamped, f'{prefix}/footprint', 5)
            self.create_subscription(TFMessage, f'/{rid}/tf',
                                     lambda msg, r=rid: self.transform(r, msg, self.tf), 10)
            self.create_subscription(TFMessage, f'/{rid}/tf_static',
                                     lambda msg, r=rid: self.transform(r, msg, self.tf_static), map_qos)
            self.create_subscription(OccupancyGrid, f'{nav}/costmap',
                                     lambda msg, r=rid: self.relay(r, msg, self.local_maps), map_qos)
            self.create_subscription(PolygonStamped, f'{nav}/published_footprint',
                                     lambda msg, r=rid: self.relay(r, msg, self.footprints), 5)

    def transform(self, rid, msg, broadcaster):
        for transform in msg.transforms:
            if transform.header.frame_id != 'map':
                transform.header.frame_id = f'{rid}/{transform.header.frame_id}'
            transform.child_frame_id = f'{rid}/{transform.child_frame_id}'
        broadcaster.sendTransform(msg.transforms)

    def relay(self, rid, msg, publishers):
        if msg.header.frame_id == 'odom':
            msg.header.frame_id = f'{rid}/odom'
            publishers[rid].publish(msg)

    def robot(self, status):
        color = self.colors.get(status.robot_id)
        if color is None:
            return
        label = Marker()
        label.header.frame_id = 'map'
        label.header.stamp = status.stamp
        label.ns = status.robot_id
        label.type = Marker.TEXT_VIEW_FACING
        label.lifetime = Duration(seconds=3).to_msg()
        label.pose.position.x = status.x
        label.pose.position.y = status.y + 0.10
        label.pose.position.z = 0.12
        label.pose.orientation.w = 1.0
        label.scale.z = 0.052
        label.color.r, label.color.g, label.color.b, label.color.a = *color, 1.0
        label.text = status.robot_id
        self.markers.publish(MarkerArray(markers=[label]))


def main():
    rclpy.init()
    node = FleetRviz()
    # [수정 2026-11-19] Ctrl-C(SIGINT)로 끝나지 않고 SIGTERM 에는 traceback 을
    # 내던 것을 고침: rclpy 가 신호를 받으면 내는 예외도 함께 잡음
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
