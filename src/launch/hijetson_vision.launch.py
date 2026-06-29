"""
hijetson_vision.launch.py

仅启动视觉模块（图像预处理 + YOLO检测 + 深度处理）
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('log_level', default_value='info'),

        Node(
            package='image_preprocess',
            executable='image_preprocess_node',
            name='image_preprocess',
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='object_detection',
            executable='object_detection_node',
            name='object_detection',
            parameters=[{
                'model_path': os.path.join(
                    os.path.dirname(__file__), '..', 'models', 'yolo', 'yolov8n.onnx'
                ),
                'conf_threshold': 0.5,
                'iou_threshold': 0.45,
                'input_width': 640,
                'input_height': 640,
            }],
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='depth_processor',
            executable='depth_processor_node',
            name='depth_processor',
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
    ])