#!/usr/bin/env python3
# [수정 2026-11-17] pinky_pro 의존 제거: pinky_pro(pinklab-art, Apache-2.0,
# 커밋 014a09f)의 pinky_bringup/bringup.py 를 그대로 복사함. 동작은 바꾸지 않음
# [수정 2026-11-18] P2(D3): 노드 이름만 원본의 pinky_bringup 에서 실행 파일과
# 같은 pinky_driver 로 바꿈
# [수정 2026-11-18] T-37: 위 커밋의 포트(/dev/ttyAMA4)는 우리 로봇과 달랐음.
# 로봇에 설치된 pinky_bringup(/dev/ttyAMA5)에 맞추고 serial_port 파라미터로 받음

import rclpy
from rclpy.node import Node
import math
import time

from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster
from tf_transformations import quaternion_from_euler
from std_msgs.msg import Float32

from .dynamixel_driver import DynamixelDriver

TWIST_SUB_TOPIC_NAME = "cmd_vel"
ODOM_PUB_TOPIC_NAME = "odom"
JOINT_PUB_TOPIC_NAME = "joint_states"
ODOM_FRAME_ID = "odom"
ODOM_CHILD_FRAME_ID = "base_footprint"

# [수정 2026-11-18] T-37: 로봇에 설치된 pinky_bringup 과 같은 포트(uart5)
SERIAL_PORT_NAME = "/dev/ttyAMA5"
BAUDRATE = 1000000
DYNAMIXEL_IDS = [1, 2] # [왼쪽 바퀴 ID, 오른쪽 바퀴 ID]

JOINT_NAME_WHEEL_L = "left_wheel_joint"
JOINT_NAME_WHEEL_R = "right_wheel_joint"

PULSE_PER_ROT = 4096 
RPM2RAD = 2 * math.pi / 60

BATTERY_VOLTAGE_TOPIC = "battery/voltage"
LOW_BATTERY_THRESHOLD = 6.8

class Pinky(Node):
    def __init__(self):
        super().__init__('pinky_driver')
        self.is_initialized = False
        
        self.get_logger().info('Initializing Pinky Bringup Node with Dynamixel...')
        
        self.declare_parameter('wheel_radius', 0.027)
        self.declare_parameter('wheel_separation', 0.0961)
        
        self.wheel_radius = self.get_parameter('wheel_radius').get_parameter_value().double_value
        self.wheel_separation = self.get_parameter('wheel_separation').get_parameter_value().double_value
        
        self.get_logger().info(f'Wheel radius: {self.wheel_radius}')
        self.get_logger().info(f'Wheel separation: {self.wheel_separation}')
        
        self.circumference = 2 * math.pi * self.wheel_radius
        # [수정 2026-11-18] T-37: 모터 직렬 포트를 파라미터로 받음
        port = self.declare_parameter('serial_port', SERIAL_PORT_NAME).value
        self.get_logger().info(f'Serial port: {port}')
        self.driver = DynamixelDriver(port, BAUDRATE, DYNAMIXEL_IDS)

        self.get_logger().info("1. Opening serial port...")
        if not self.driver.begin():
            self.get_logger().error("Failed to open serial port! Shutting down.")
            return

        self.get_logger().info("2. Initializing motors...")
        if not self.driver.initialize_motors():
            self.get_logger().error("Failed to initialize motors! Shutting down.")
            self.driver.terminate()
            return
        
        self.get_logger().info("Waiting for motors to be ready...")
        time.sleep(1.0)

        self.get_logger().info("3. Setting initial RPM to zero...")
        if not self.driver.set_double_rpm(0, 0):
            self.get_logger().error("Failed to set initial RPM! Shutting down.")
            self.driver.terminate()
            return

        self.get_logger().info("4. Reading initial encoder values...")
        _, _, self.last_encoder_l, self.last_encoder_r = self.driver.get_feedback()
        if self.last_encoder_l is None:
            self.get_logger().error("Failed to read initial encoder position! Shutting down.")
            self.driver.terminate()
            return

        self.get_logger().info(f"Initial Encoder read: L={self.last_encoder_l}, R={self.last_encoder_r}. Controller is responsive.")
            
        # [수정 2026-11-17] A1: 속도 명령 감시. cmd_vel 이 cmd_vel_timeout 초
        # 넘게 끊기면 0 RPM 을 보냄(0 이하면 감시 안 함). 다이나믹셀은 속도
        # 모드라 마지막 RPM 을 유지하므로, 보내는 쪽(Nav2, mobile_controller,
        # 네트워크)이 죽으면 로봇이 그 속도로 계속 갔음
        self.cmd_timeout = self.declare_parameter(
            'cmd_vel_timeout', 0.5).value
        self._cmd_time = time.monotonic()   # 마지막 cmd_vel 수신 시각
        self._stop_pending = False   # 0 이 아닌 명령을 보냈고 아직 세우지 않음
        self._zero_failed = False    # 0 속도 명령의 전송이 실패함

        self.odom_pub = self.create_publisher(Odometry, ODOM_PUB_TOPIC_NAME, 10)
        self.joint_pub = self.create_publisher(JointState, JOINT_PUB_TOPIC_NAME, 10)
        self.twist_sub = self.create_subscription(Twist, TWIST_SUB_TOPIC_NAME, self.twist_callback, 10)
        self.tf_broadcaster = TransformBroadcaster(self)
        self.timer = self.create_timer(1.0 / 30.0, self.update_and_publish)

        self.battery_sub = self.create_subscription(
            Float32,
            BATTERY_VOLTAGE_TOPIC,
            self.battery_voltage_callback,
            10
        )

        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.last_time = self.get_clock().now()
        self.is_initialized = True
        self.get_logger().info('Pinky Bringup with Dynamixel has been started successfully.')

    def twist_callback(self, msg: Twist):
        linear_x = msg.linear.x
        angular_z = msg.angular.z

        v_l = linear_x - (angular_z * self.wheel_separation / 2.0)
        v_r = linear_x + (angular_z * self.wheel_separation / 2.0)

        wheel_rads_l = v_l / self.wheel_radius
        wheel_rads_r = v_r / self.wheel_radius

        rpm_l = wheel_rads_l * 60.0 / (2 * math.pi)
        rpm_r = -wheel_rads_r * 60.0 / (2 * math.pi)

        max_val = max(abs(rpm_l), abs(rpm_r))
        MAX_RPM = 100.0
        if max_val > MAX_RPM:
            scale = MAX_RPM / max_val
            rpm_l *= scale
            rpm_r *= scale

        # [수정 2026-11-17] A1: 0 이 아닌 명령은 보내기 전에 "정지 필요"로
        # 표시하고, 0 RPM 전송이 성공했을 때만 지움. 0 명령 전송이 실패하면
        # 다음 주기(30 Hz)에 _watch_cmd_vel 이 바로 다시 보냄
        moving = abs(rpm_l) > 1e-6 or abs(rpm_r) > 1e-6
        self._cmd_time = time.monotonic()
        if moving:
            self._stop_pending, self._zero_failed = True, False
        if not self.driver.set_double_rpm(rpm_l, rpm_r):
            self.get_logger().warn("Failed to send motor command.")
            if not moving:
                self._zero_failed = True
        elif not moving:
            self._stop_pending = self._zero_failed = False

    # [수정 2026-11-17] 신규 (A1): 속도 명령 시간 초과 감시
    def _watch_cmd_vel(self) -> None:
        """명령이 끊겼거나 정지 전송이 실패했으면 0 RPM 을 보낸다.

        update_and_publish(30 Hz)의 맨 앞에서 불린다. 전송에 실패하면 표시를
        남겨 다음 주기에 다시 시도한다. 전송 성공은 패킷을 보냈다는 뜻이며
        실제 정지 여부는 오도메트리로 확인한다(실기기 확인 필요).
        """
        silent = time.monotonic() - self._cmd_time
        timed_out = (self._stop_pending and self.cmd_timeout > 0
                     and silent > self.cmd_timeout)
        if not (timed_out or self._zero_failed):
            return
        if self.driver.set_double_rpm(0, 0):
            self._stop_pending = self._zero_failed = False
            if timed_out:
                self.get_logger().warn(
                    f'cmd_vel silent for {silent:.2f} s: motors stopped')
        else:
            self.get_logger().warn(
                'Failed to send the stop command, retrying.',
                throttle_duration_sec=1.0)

    def update_and_publish(self):
        self._watch_cmd_vel()
        current_time = self.get_clock().now()
        dt = (current_time - self.last_time).nanoseconds / 1e9
        if dt <= 0: return

        feedback = self.driver.get_feedback()
        if feedback[0] is None:
            self.get_logger().warn("Failed to read motor data. Skipping update cycle.")
            return
        rpm_l, rpm_r, encoder_l, encoder_r = feedback

        delta_l = encoder_l - self.last_encoder_l
        delta_r = -(encoder_r - self.last_encoder_r)
        
        self.last_encoder_l = encoder_l
        self.last_encoder_r = encoder_r

        dist_l = (delta_l / PULSE_PER_ROT) * self.circumference
        dist_r = (delta_r / PULSE_PER_ROT) * self.circumference

        delta_distance = (dist_r + dist_l) / 2.0
        delta_theta = (dist_r - dist_l) / self.wheel_separation
        
        self.theta += delta_theta
        self.x += delta_distance * math.cos(self.theta)
        self.y += delta_distance * math.sin(self.theta)
        
        v_x = delta_distance / dt if dt > 0 else 0.0
        vth = delta_theta / dt if dt > 0 else 0.0

        self._publish_tf(current_time)
        self._publish_odometry(current_time, v_x, vth)
        self._publish_joint_states(current_time, rpm_l, rpm_r)

        self.last_time = current_time

    def _publish_tf(self, current_time):
        t = TransformStamped()
        t.header.stamp = current_time.to_msg()
        t.header.frame_id = ODOM_FRAME_ID
        t.child_frame_id = ODOM_CHILD_FRAME_ID
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        q = quaternion_from_euler(0, 0, self.theta)
        t.transform.rotation.x, t.transform.rotation.y, t.transform.rotation.z, t.transform.rotation.w = q
        self.tf_broadcaster.sendTransform(t)

    def _publish_odometry(self, current_time, v_x, vth):
        odom_msg = Odometry()
        odom_msg.header.stamp = current_time.to_msg()
        odom_msg.header.frame_id = ODOM_FRAME_ID
        odom_msg.child_frame_id = ODOM_CHILD_FRAME_ID
        odom_msg.pose.pose.position.x, odom_msg.pose.pose.position.y = self.x, self.y
        q = quaternion_from_euler(0, 0, self.theta)
        odom_msg.pose.pose.orientation.x, odom_msg.pose.pose.orientation.y, odom_msg.pose.pose.orientation.z, odom_msg.pose.pose.orientation.w = q
        odom_msg.twist.twist.linear.x, odom_msg.twist.twist.angular.z = v_x, vth
        self.odom_pub.publish(odom_msg)

    def _publish_joint_states(self, current_time, rpm_l, rpm_r):
        joint_msg = JointState()
        joint_msg.header.stamp = current_time.to_msg()
        joint_msg.name = [JOINT_NAME_WHEEL_L, JOINT_NAME_WHEEL_R]
        
        pos_l_rad = (self.last_encoder_l / PULSE_PER_ROT) * (2 * math.pi)
        pos_r_rad = (self.last_encoder_r / PULSE_PER_ROT) * (2 * math.pi)
        joint_msg.position = [pos_l_rad, pos_r_rad]
        joint_msg.velocity = [rpm_l * RPM2RAD, rpm_r * RPM2RAD]

        self.joint_pub.publish(joint_msg)

    def battery_voltage_callback(self, msg):
        self.current_voltage = msg.data
        
        if self.current_voltage is None:
            self.get_logger().warn("Battery voltage data has not been received yet.")
        elif self.current_voltage <= LOW_BATTERY_THRESHOLD:
            self.get_logger().warn(
                f"!!! LOW BATTERY WARNING !!! Voltage: {self.current_voltage:.2f}V. Please charge the robot."
            )


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = Pinky()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.driver.terminate()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()