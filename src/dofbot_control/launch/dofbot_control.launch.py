# -*- coding: utf-8 -*-
"""控制模块启动文件: 正逆解服务器 + 控制服务 + 分拣闭环 + 事件桥接(可选仿真检测)。

用法:
  ros2 launch dofbot_control dofbot_control.launch.py
  ros2 launch dofbot_control dofbot_control.launch.py with_fake_detect:=true
  ros2 launch dofbot_control dofbot_control.launch.py with_event_bridge:=true
  ros2 launch dofbot_control dofbot_control.launch.py config_file:=/path/to/dofbot_config.yaml
"""
import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('dofbot_control')
    default_config = os.path.join(pkg_share, 'config', 'dofbot_config.yaml')

    config_arg = DeclareLaunchArgument(
        'config_file', default_value=default_config,
        description='dofbot_config.yaml 路径')
    fake_detect_arg = DeclareLaunchArgument(
        'with_fake_detect', default_value='false', choices=['true', 'false'],
        description='是否同时启动仿真检测发布器(联调用)')
    bridge_arg = DeclareLaunchArgument(
        'with_event_bridge', default_value='false', choices=['true', 'false'],
        description='是否启动 task_event 事件桥接(上报到记录服务 /api/events)')

    # 任务2 正逆运动学解算服务器(反解失败时返回 NaN 关节角)
    kinemarics_server = Node(
        package='dofbot_moveit', executable='dofbot_server',
        name='dofbot_kinemarics_server', output='screen')

    # 控制服务: pick_place / task_command / 动作组 / 事件上报
    control_server = Node(
        package='dofbot_control', executable='dofbot_control_server',
        name='dofbot_control_server', output='screen',
        parameters=[{'config_file': LaunchConfiguration('config_file')}])

    # 分拣闭环: 订阅检测结果 -> 标定转换 -> 提交 pick_place
    sorter = Node(
        package='dofbot_control', executable='dofbot_sorter',
        name='dofbot_sorter', output='screen',
        parameters=[{'config_file': LaunchConfiguration('config_file')}])

    # task_event HTTP 桥接: 订阅 /task_event -> POST /api/events(朱玉贺 -> 严晨越)
    event_bridge = Node(
        package='dofbot_control', executable='dofbot_event_bridge',
        name='dofbot_event_bridge', output='screen',
        condition=IfCondition(LaunchConfiguration('with_event_bridge')),
        parameters=[{'config_file': LaunchConfiguration('config_file')}])

    # 仿真检测发布器(仅联调)
    fake_detect = Node(
        package='dofbot_control', executable='fake_detect',
        name='fake_detect', output='screen',
        condition=IfCondition(LaunchConfiguration('with_fake_detect')),
        arguments=['--random', '5'])

    return LaunchDescription([
        config_arg,
        fake_detect_arg,
        bridge_arg,
        kinemarics_server,
        control_server,
        sorter,
        event_bridge,
        fake_detect,
    ])
