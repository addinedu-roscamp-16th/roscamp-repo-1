"""Expose separate robot odometry frames in one read-only RViz view."""
import rclpy
from geometry_msgs.msg import PolygonStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from tf2_msgs.msg import TFMessage
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
from visualization_msgs.msg import Marker, MarkerArray

from frybot_interfaces.msg import RobotStatus


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
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
