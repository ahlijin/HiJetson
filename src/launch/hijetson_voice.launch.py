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
            parameters=[{
                'sample_rate': 16000,
                'frame_size': 1600,
                'device_index': 0,    # ASTRA Pro USB Audio
                'channels': 2,         # ASTRA Pro is stereo
            }],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_vad',
            executable='voice_vad_node',
            name='voice_vad',
            output='screen',
            parameters=[{
                'sample_rate': 16000,
                'frame_ms': 30,
                'silence_timeout': 0.5,
                'vad_mode': 1,
            }],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
        Node(
            package='voice_asr',
            executable='voice_asr_node',
            name='voice_asr',
            output='screen',
            parameters=[{
                'model_size': 'tiny',      # tiny/base/small/medium/large
                'device': 'cuda',
                'language': 'zh',
                'sample_rate': 16000,
            }],
            arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
        ),
    ])
