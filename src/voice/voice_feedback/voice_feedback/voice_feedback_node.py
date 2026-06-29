#!/usr/bin/env python3
"""
voice_feedback_node.py

Audio feedback node. Subscribes to wake word and ASR result topics,
and plays short beep tones through the system's audio output device
to inform the user of system state changes.

Subscribes:
  /voice/wake_word (std_msgs/String) — Plays a rising tone "🔊 listening" beep
  /voice/asr_result (std_msgs/String) — Plays a confirmation beep when command is recognized

Configuration (from voice_params.yaml):
  ~device_index (int) — Output device index (-1 = default output)
  ~wake_volume (float) — Volume for wake beep (0.0–1.0, default 0.5)
  ~result_volume (float) — Volume for result beep (0.0–1.0, default 0.3)
  ~sample_rate (int) — Output sample rate (default 48000)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import numpy as np
import sounddevice as sd


class VoiceFeedbackNode(Node):
    def __init__(self):
        super().__init__('voice_feedback')

        # Parameters
        self.device_index = self.declare_parameter('device_index', -1).value
        self.wake_volume = self.declare_parameter('wake_volume', 0.5).value
        self.result_volume = self.declare_parameter('result_volume', 0.3).value
        self.sample_rate = self.declare_parameter('sample_rate', 48000).value

        # Subscribers
        self._ww_sub = self.create_subscription(
            String, '/voice/wake_word', self.wake_word_callback, 10
        )
        self._asr_sub = self.create_subscription(
            String, '/voice/asr_result', self.asr_result_callback, 10
        )

        self.get_logger().info(
            f'VoiceFeedbackNode started: device={self.device_index}, '
            f'wake_vol={self.wake_volume}, result_vol={self.result_volume}'
        )

    def _play_tone(self, frequencies, durations, volume=0.5):
        """
        Generate and play a multi-tone sequence.
        
        Args:
            frequencies: List of frequencies in Hz for each segment
            durations: List of durations in seconds for each segment
            volume: Amplitude multiplier (0.0–1.0)
        """
        try:
            segments = []
            for freq, dur in zip(frequencies, durations):
                t = np.linspace(0, dur, int(self.sample_rate * dur), endpoint=False)
                # Sine wave with fade-in/out to avoid click
                envelope = np.ones_like(t)
                fade_len = min(int(0.02 * self.sample_rate), len(t) // 4)
                if fade_len > 0:
                    envelope[:fade_len] = np.linspace(0, 1, fade_len)
                    envelope[-fade_len:] = np.linspace(1, 0, fade_len)
                segment = np.sin(2 * np.pi * freq * t) * envelope * volume
                segments.append(segment)

            audio = np.concatenate(segments).astype(np.float32)

            # Play through output device
            sd.play(audio, samplerate=self.sample_rate, device=self.device_index if self.device_index >= 0 else None)
            # Don't block — let it play asynchronously

        except Exception as e:
            self.get_logger().warning(f'Failed to play audio: {e}', throttle_duration_sec=10.0)

    def wake_word_callback(self, msg: String):
        """Wake word detected — play a rising two-tone beep (like "listening" feedback)."""
        self.get_logger().info(f'🔊 Wake word feedback: "{msg.data}"')
        # Rising tone: 800Hz → 1200Hz, 150ms each
        self._play_tone(
            frequencies=[800, 1200],
            durations=[0.15, 0.15],
            volume=self.wake_volume,
        )

    def asr_result_callback(self, msg: String):
        """ASR result received — play a short confirmation beep."""
        self.get_logger().debug(f'ASR result feedback: "{msg.data}"')
        # Short single tone: 1000Hz, 100ms
        self._play_tone(
            frequencies=[1000],
            durations=[0.1],
            volume=self.result_volume,
        )


def main(args=None):
    rclpy.init(args=args)
    node = VoiceFeedbackNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()