#!/usr/bin/env python3
"""
voice_vad_node.py

Voice Activity Detection using webrtcvad.
Subscribes to /voice/audio_raw (Float32MultiArray), detects speech segments,
and publishes complete audio clips to /voice/audio_clip when silence is detected.

Publishes:
  /voice/voice_activity (std_msgs/Bool) - Whether speech is currently active
  /voice/audio_clip (std_msgs/Float32MultiArray) - Complete audio clip when speech ends
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, MultiArrayDimension, Bool
import numpy as np
import webrtcvad


class VoiceVADNode(Node):
    def __init__(self):
        super().__init__('voice_vad_node')

        self.sample_rate = self.declare_parameter('sample_rate', 16000).value
        self.frame_ms = self.declare_parameter('frame_ms', 30).value  # 30ms for webrtcvad
        self.silence_timeout = self.declare_parameter('silence_timeout', 0.5).value  # seconds
        self.vad_mode = self.declare_parameter('vad_mode', 1).value  # 0-3, more aggressive

        # webrtcvad requires 16-bit PCM, 16kHz, 30ms frames (480 samples)
        self.vad = webrtcvad.Vad(self.vad_mode)
        self.frame_samples = int(self.sample_rate * self.frame_ms / 1000)

        self.activity_pub = self.create_publisher(Bool, '/voice/voice_activity', 10)
        self.clip_pub = self.create_publisher(Float32MultiArray, '/voice/audio_clip', 10)
        self.sub = self.create_subscription(
            Float32MultiArray, '/voice/audio_raw', self.audio_callback, 10
        )

        self.audio_buffer = np.array([], dtype=np.float32)
        self.speech_active = False
        self.silence_frames = 0
        self.silence_max_frames = int(self.silence_timeout / (self.frame_ms / 1000))

        self.get_logger().info(
            f'VoiceVADNode started: mode={self.vad_mode}, '
            f'silence_timeout={self.silence_timeout}s'
        )

    def audio_callback(self, msg: Float32MultiArray):
        audio = np.array(msg.data, dtype=np.float32)

        # webrtcvad expects int16 PCM
        audio_int16 = (audio * 32767).astype(np.int16)

        # Process in VAD-sized frames
        for i in range(0, len(audio_int16), self.frame_samples):
            frame = audio_int16[i:i + self.frame_samples]
            if len(frame) < self.frame_samples:
                continue

            is_speech = self.vad.is_speech(frame.tobytes(), self.sample_rate)

            if is_speech:
                if not self.speech_active:
                    self.speech_active = True
                    self.audio_buffer = np.array([], dtype=np.float32)
                    self.get_logger().debug('Speech started')

                self.silence_frames = 0
                # Convert back to float32 for buffer
                self.audio_buffer = np.concatenate([
                    self.audio_buffer, frame.astype(np.float32) / 32767.0
                ])
            else:
                if self.speech_active:
                    self.silence_frames += 1
                    # Keep trailing audio in buffer for continuity
                    self.audio_buffer = np.concatenate([
                        self.audio_buffer, frame.astype(np.float32) / 32767.0
                    ])

                    if self.silence_frames >= self.silence_max_frames:
                        self._publish_clip()
                        self.speech_active = False
                        self.audio_buffer = np.array([], dtype=np.float32)
                        self.silence_frames = 0
                        self.get_logger().debug('Speech ended')

        # Publish activity status
        activity_msg = Bool()
        activity_msg.data = self.speech_active
        self.activity_pub.publish(activity_msg)

    def _publish_clip(self):
        if len(self.audio_buffer) == 0:
            return

        # Trim leading silence (keep first speech frame)
        # Trim trailing silence (keep last speech + timeout)
        trim_samples = min(
            self.silence_max_frames * self.frame_samples,
            len(self.audio_buffer) // 4
        )
        trimmed = self.audio_buffer[:-trim_samples] if trim_samples > 0 else self.audio_buffer

        if len(trimmed) < self.frame_samples * 2:
            return  # Too short, likely noise

        msg = Float32MultiArray()
        msg.layout.dim.append(MultiArrayDimension(
            label='samples', size=len(trimmed), stride=1
        ))
        msg.data = trimmed.tolist()
        self.clip_pub.publish(msg)
        self.get_logger().info(f'Published audio clip: {len(trimmed)} samples ({len(trimmed)/self.sample_rate:.2f}s)')


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