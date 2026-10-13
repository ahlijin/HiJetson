"""
hijetson_vision.launch.py

视觉模块：Astra Pro 相机 + 深度处理

注意（2026-10 整理）：
  原来的 image_preprocess / object_detection 两个包在本仓库里并不存在，launch 里引用它们
  必然报 "package not found"，已移除。等真正实现后再加回来（或恢复注释里的节点）。
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 相机: 复用 jetauto_peripherals 里的 Astra 包装（与 Pi3 侧共用一份参数）
    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('jetauto_peripherals'),
            'launch', 'depth_camera.launch.py')),
    )

    return LaunchDescription([
        DeclareLaunchArgument('log_level', default_value='info'),

        camera_launch,

        # TODO: 图像预处理 / YOLO 检测（image_preprocess / object_detection 尚未实现）
        # Node(package='image_preprocess', executable='image_preprocess_node', ...),
        # Node(package='object_detection', executable='object_detection_node',
        #      parameters=[{'model_path': ..., 'conf_threshold': 0.5}], ...),

        Node(
            package='depth_processor',
            executable='depth_processor_node',
            name='depth_processor',
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
    ])
