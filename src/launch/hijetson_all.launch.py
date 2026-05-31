"""
hijetson_all.launch.py

HiJetson 完整启动文件
启动所有语音、视觉和融合节点
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


def generate_launch_description():
    return LaunchDescription([
        # ===== 全局参数 =====
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('log_level', default_value='info'),

        # ===== 语音模块 =====
        GroupAction([
            PushRosNamespace('voice'),

            # 语音采集
            Node(
                package='voice_capture',
                executable='voice_capture_node',
                name='voice_capture',
                parameters=[{
                    'sample_rate': 16000,
                    'frame_size': 1600,
                    'device_index': -1,
                }],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 语音活动检测
            Node(
                package='voice_vad',
                executable='voice_vad_node',
                name='voice_vad',
                parameters=[{
                    'sample_rate': 16000,
                    'frame_ms': 30,
                    'silence_timeout': 0.5,
                    'vad_mode': 1,
                }],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 语音识别
            Node(
                package='voice_asr',
                executable='voice_asr_node',
                name='voice_asr',
                parameters=[{
                    'model_size': 'base',
                    'device': 'cuda',
                    'compute_type': 'float16',
                    'language': 'zh',
                }],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),
        ]),

        # ===== 视觉模块 =====
        GroupAction([
            PushRosNamespace('vision'),

            # 图像预处理
            Node(
                package='image_preprocess',
                executable='image_preprocess_node',
                name='image_preprocess',
                parameters=[{
                    'input_width': 640,
                    'input_height': 640,
                }],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 目标检测 (YOLO)
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
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 深度处理
            Node(
                package='depth_processor',
                executable='depth_processor_node',
                name='depth_processor',
                parameters=[{
                    'max_depth': 10.0,
                }],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),
        ]),

        # ===== 融合模块 =====
        Node(
            package='fusion_node',
            executable='fusion_node',
            name='fusion_node',
            parameters=[],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
            output='screen',
        ),
    ])