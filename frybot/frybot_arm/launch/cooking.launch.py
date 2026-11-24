"""Frybot Cooking Package 만 띄운다 (Master Controller + Arm Controller A/B).

  ros2 launch frybot_arm cooking.launch.py
  ros2 launch frybot_arm cooking.launch.py ai_host:=192.168.0.10

[수정 2026-11-18] P2: 삭제된 인자(real.launch.py 의 sim_cooking) 언급을 뺌.
sim.launch.py(가상 매장)는 같은 노드를 직접 띄우므로 함께 실행하지 않습니다.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration as LC

from frybot_arm.cooking import cooking_nodes


def _setup(context):
    return cooking_nodes(
        undercooked_prob=float(LC('undercooked_prob').perform(context)),
        ai_host=LC('ai_host').perform(context))


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('undercooked_prob', default_value='0.25'),
        DeclareLaunchArgument('ai_host', default_value='127.0.0.1'),
        OpaqueFunction(function=_setup)])
