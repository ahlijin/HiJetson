"""
hijetson_voice.launch.py

仅启动语音模块（语音采集 + VAD + 唤醒词 + ASR）
从 src/config/voice_params.yaml 加载参数
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 获取 config 文件路径
    launch_dir = os.path.dirname(os.path.realpath(__file__))
    config_file = os.path.join(launch_dir, '..', 'config', 'voice_params.yaml')
    config_file = os.path.abspath(config_file)

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
