import os
from launch_ros.actions import Node
from launch import LaunchDescription
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument


def generate_launch_description():
    debug_arg = DeclareLaunchArgument('debug', default_value='false')

    lidar_controller_node = Node(
        package='jetauto_app',
        executable='lidar_controller',
        output='screen',
    )

    return LaunchDescription([
        debug_arg,
        lidar_controller_node,
    ])
