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
    # 获取 config 文件路径
    launch_dir = os.path.dirname(os.path.realpath(__file__))
    config_file = os.path.join(launch_dir, '..', 'config', 'voice_params.yaml')
    config_file = os.path.abspath(config_file)

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
                parameters=[config_file],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 语音活动检测
            Node(
                package='voice_vad',
                executable='voice_vad_node',
                name='voice_vad',
                parameters=[config_file],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 唤醒词检测
            Node(
                package='voice_wake_word',
                executable='voice_wake_word_node',
                name='voice_wake_word',
                parameters=[config_file],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 语音反馈提示音
            Node(
                package='voice_feedback',
                executable='voice_feedback_node',
                name='voice_feedback',
                parameters=[config_file],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),

            # 语音识别
            Node(
                package='voice_asr',
                executable='voice_asr_node',
                name='voice_asr',
                parameters=[config_file],
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