from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # [수정 2026-11-18] P2: RViz 설정 이름 fleet_real.rviz -> fleet.rviz
    config = (Path(get_package_share_directory('frybot_bringup'))
              / 'rviz' / 'fleet.rviz')
    return LaunchDescription([
        Node(package='frybot_bringup', executable='fleet_rviz', output='screen'),
        Node(package='rviz2', executable='rviz2', output='screen', arguments=['-d', str(config)]),
    ])
