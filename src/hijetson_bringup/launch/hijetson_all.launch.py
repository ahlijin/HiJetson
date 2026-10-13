"""
hijetson_all.launch.py

HiJetson 完整启动：Astra Pro 相机 + 语音链路 + 深度处理 + 融合 + 声源跟踪
参数从 config/voice_params.yaml 加载（随本包安装到 share/hijetson_bringup/config/）

用法：
    source /opt/ros/humble/setup.bash && source /opt/hijetson/install/setup.bash
    ros2 launch hijetson_bringup hijetson_all.launch.py

注意（2026-10 整理）：
  - 原来引用的 image_preprocess / object_detection 两个包本仓库并不存在，已移除（见 TODO）
  - voice_executor（真正执行移动指令的节点）**没有**包含在这里，需要时单开 hijetson_voice.launch.py
    或自己加进来，避免一启动就整车动
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


def generate_launch_description():
    config_file = os.path.join(
        get_package_share_directory('hijetson_bringup'), 'config', 'voice_params.yaml')

    # 相机放在根命名空间（与 scripts/run_*.sh 以前的做法一致：/camera/... 话题）
    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('jetauto_peripherals'),
            'launch', 'depth_camera.launch.py')),
    )

    return LaunchDescription([
        # ===== 全局参数 =====
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('log_level', default_value='info'),

        # ===== 相机 (Astra Pro) =====
        camera_launch,

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
                package='voice_hotword',
                executable='voice_hotword_node',
                name='voice_hotword',
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

            # 声源定位 (XVF3000 DOA)
            Node(
                package='voice_doa',
                executable='voice_doa_node',
                name='voice_doa',
                parameters=[config_file],
                arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
                output='screen',
            ),
        ]),

        # ===== 视觉模块 =====
        GroupAction([
            PushRosNamespace('vision'),

            # TODO: 图像预处理 / YOLO 检测（image_preprocess / object_detection 尚未实现，
            #       原 launch 里引用了它们，必然报 package not found，先移除以保证能起）
            # Node(package='image_preprocess', executable='image_preprocess_node', ...),
            # Node(package='object_detection', executable='object_detection_node', ...),

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

        # ===== 行为模块 =====
        # 声源跟踪：DOA → 舵机云台
        Node(
            package='jetauto_app',
            executable='servo_tracker',
            name='servo_tracker',
            parameters=[{
                'servo_pan_id': 1,
                'center_pulse': 500,
                'range_pulse': 188,
                'angle_range': 180.0,
                'invert': False,
                'pulse_min': 312,
                'pulse_max': 688,
            }],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
            output='screen',
        ),
    ])
