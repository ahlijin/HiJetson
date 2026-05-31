"""
hijetson_voice.launch.py

仅启动语音模块（语音采集 + VAD + ASR）
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('log_level', default_value='info'),

        Node(
            package='voice_capture',
            executable='voice_capture_node',
            name='voice_capture',
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_vad',
            executable='voice_vad_node',
            name='voice_vad',
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_asr',
            executable='voice_asr_node',
            name='voice_asr',
            output='screen',
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
    ])