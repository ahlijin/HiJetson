#!/usr/bin/env python3
"""
voice_vad_node.py

Voice Activity Detection using XVF3000 hardware VAD signal.
Subscribes to /voice/vad_hw (Bool) for speech/silence state and
/voice/audio_raw (Float32MultiArray) for audio buffering.

Publishes:
  /voice/voice_activity (std_msgs/Bool) — whether speech is currently active
  /voice/audio_clip (std_msgs/Float32MultiArray) — complete audio clip when speech ends

Parameters (~voice_vad):
  sample_rate     (int)   Audio sample rate (default: 16000)
  frame_ms        (int)   Frame size in ms for buffering (default: 30)
  silence_timeout (float) Seconds of silence before clip is finalised (default: 0.5)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, MultiArrayDimension, Bool
import numpy as np


class VoiceVADNode(Node):
    def __init__(self):
        super().__init__('voice_vad_node')

        self.sample_rate = self.declare_parameter('sample_rate', 16000).value
        self.frame_ms = self.declare_parameter('frame_ms', 30).value
        self.silence_timeout = self.declare_parameter('silence_timeout', 0.5).value

        self.frame_samples = int(self.sample_rate * self.frame_ms / 1000)
        self.silence_max_frames = int(self.silence_timeout / (self.frame_ms / 1000))

        # Publishers
        self.activity_pub = self.create_publisher(Bool, '/voice/voice_activity', 10)
        self.clip_pub = self.create_publisher(Float32MultiArray, '/voice/audio_clip', 10)

        # Subscribers
        self.audio_sub = self.create_subscription(
            Float32MultiArray, '/voice/audio_raw', self.audio_callback, 10
        )
        self.vad_sub = self.create_subscription(
            Bool, '/voice/vad_hw', self.vad_callback, 10
        )

        # State
        self.audio_buffer = np.array([], dtype=np.float32)
        self.speech_active = False
        self.silence_frames = 0
        self._hw_vad = False

        self.get_logger().info(
            f'VAD started: source=hw (XVF3000), '
            f'silence_timeout={self.silence_timeout}s'
        )

    def vad_callback(self, msg: Bool):
        self._hw_vad = msg.data

    def audio_callback(self, msg: Float32MultiArray):
        audio = np.array(msg.data, dtype=np.float32)

        for i in range(0, len(audio), self.frame_samples):
            frame = audio[i:i + self.frame_samples]
            if len(frame) < self.frame_samples:
                continue
            # 能量 VAD：RMS > 阈值即视为有声（10x增益后噪声~0.01，语音~0.15+）
            frame_rms = np.sqrt(np.mean(frame ** 2))
            is_speech = frame_rms > 0.03
            self._feed(is_speech, frame)

        self._publish_activity()

    def _feed(self, is_speech: bool, frame: np.ndarray):
        if is_speech:
            if not self.speech_active:
                self.speech_active = True
                self.audio_buffer = np.array([], dtype=np.float32)
                self.get_logger().debug('Speech started')

            self.silence_frames = 0
            self.audio_buffer = np.concatenate([self.audio_buffer, frame])
        else:
            if self.speech_active:
                self.silence_frames += 1
                self.audio_buffer = np.concatenate([self.audio_buffer, frame])

                if self.silence_frames >= self.silence_max_frames:
                    self._publish_clip()
                    self.speech_active = False
                    self.audio_buffer = np.array([], dtype=np.float32)
                    self.silence_frames = 0
                    self.get_logger().debug('Speech ended')

    def _publish_activity(self):
        msg = Bool()
        msg.data = self.speech_active
        self.activity_pub.publish(msg)

    def _publish_clip(self):
        if len(self.audio_buffer) == 0:
            return

        trim_samples = min(
            self.silence_max_frames * self.frame_samples,
            len(self.audio_buffer) // 4
        )
        trimmed = self.audio_buffer[:-trim_samples] if trim_samples > 0 else self.audio_buffer

        if len(trimmed) < self.frame_samples * 2:
            return

        msg = Float32MultiArray()
        msg.layout.dim.append(MultiArrayDimension(
            label='samples', size=len(trimmed), stride=1
        ))
        msg.data = trimmed.tolist()
        self.clip_pub.publish(msg)
        self.get_logger().info(
            f'Published audio clip: {len(trimmed)} samples '
            f'({len(trimmed)/self.sample_rate:.2f}s)'
        )


def main(args=None):
    rclpy.init(args=args)
    node = VoiceVADNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
