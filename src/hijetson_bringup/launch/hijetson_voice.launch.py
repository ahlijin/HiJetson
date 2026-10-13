"""
hijetson_voice.launch.py

仅启动语音模块（语音采集 + VAD + 唤醒词 + 反馈音 + ASR + DOA + 声源跟踪 + 指令执行）
参数从 config/voice_params.yaml 加载（随本包一起安装到 share/hijetson_bringup/config/）

用法（容器内/设备上）：
    source /opt/ros/humble/setup.bash
    source /opt/hijetson/install/setup.bash
    ros2 launch hijetson_bringup hijetson_voice.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_file = os.path.join(
        get_package_share_directory('hijetson_bringup'), 'config', 'voice_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('log_level', default_value='info'),

        Node(
            package='voice_capture',
            executable='voice_capture_node',
            name='voice_capture',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_vad',
            executable='voice_vad_node',
            name='voice_vad',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_hotword',
            executable='voice_hotword_node',
            name='voice_hotword',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_feedback',
            executable='voice_feedback_node',
            name='voice_feedback',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_asr',
            executable='voice_asr_node',
            name='voice_asr',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        # 声源定位 (XVF3000 DOA)
        Node(
            package='voice_doa',
            executable='voice_doa_node',
            name='voice_doa',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        # 舵机声源跟踪 + 小车自动旋转
        Node(
            package='jetauto_app',
            executable='servo_tracker',
            name='servo_tracker',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        # 语音指令执行器
        Node(
            package='voice_executor',
            executable='voice_executor_node',
            name='voice_executor',
            output='screen',
            parameters=[config_file],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
    ])
