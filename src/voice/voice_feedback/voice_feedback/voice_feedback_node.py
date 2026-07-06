#!/usr/bin/env python3
"""
voice_feedback_node.py

Multi-modal feedback on wake word / ASR events:
  - Audio tone  (through speaker / PulseAudio)
  - Buzzer beep (through STM32 / ros_robot_controller)
  - LED flash   (ReSpeaker pixel ring)

Subscribes:
  /voice/wake_word  (std_msgs/String)  — trigger wake feedback
  /voice/asr_result (std_msgs/String)  — trigger result beep

Publishes:
  /ros_robot_controller/set_buzzer  (BuzzerState)  — STM32 buzzer beep
  /voice/status_led                  (ColorRGBA)    — LED colour flash

Configuration (from voice_params.yaml):
  device_index     (int)   Audio output device (-1 = default)
  wake_volume      (float) Audio tone volume 0-1  (default 0.5)
  result_volume    (float) ASR result tone volume (default 0.3)
  sample_rate      (int)   Output sample rate (default 48000)
  buzzer_freq      (int)   STM32 buzzer frequency (default 800, lower = quieter)
  buzzer_on_time   (float) Buzzer on duration sec (default 0.12)
  led_r/g/b/a      (float) LED flash colour (default 0.0 0.5 1.0 1.0 = cyan)
  led_duration     (float) LED flash duration sec before restoring trace (default 2.0)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, ColorRGBA
from ros_robot_controller_msgs.msg import BuzzerState
import numpy as np
import sounddevice as sd


class VoiceFeedbackNode(Node):
    def __init__(self):
        super().__init__('voice_feedback')

        # ── Audio parameters ──
        self.device_index = self.declare_parameter('device_index', -1).value
        self.wake_volume = self.declare_parameter('wake_volume', 0.5).value
        self.result_volume = self.declare_parameter('result_volume', 0.3).value
        self.sample_rate = self.declare_parameter('sample_rate', 48000).value

        # ── Buzzer parameters ──
        self.buzzer_freq = self.declare_parameter('buzzer_freq', 800).value
        self.buzzer_on_time = self.declare_parameter('buzzer_on_time', 0.12).value

        # ── LED parameters ──
        self._led_r = self.declare_parameter('led_r', 0.0).value
        self._led_g = self.declare_parameter('led_g', 0.5).value
        self._led_b = self.declare_parameter('led_b', 1.0).value
        self._led_a = self.declare_parameter('led_a', 1.0).value
        self._led_duration = self.declare_parameter('led_duration', 2.0).value

        # ── Publishers ──
        self._buzzer_pub = self.create_publisher(
            BuzzerState, '/ros_robot_controller/set_buzzer', 1
        )
        self._led_pub = self.create_publisher(
            ColorRGBA, '/voice/status_led', 1
        )

        # ── Subscribers ──
        self._ww_sub = self.create_subscription(
            String, '/voice/wake_word', self.wake_word_callback, 10
        )
        self._asr_sub = self.create_subscription(
            String, '/voice/asr_result', self.asr_result_callback, 10
        )

        self.get_logger().info(
            f'VoiceFeedbackNode started: '
            f'buzzer={self.buzzer_freq}Hz/{self.buzzer_on_time}s, '
            f'led=({self._led_r},{self._led_g},{self._led_b})/{self._led_duration}s'
        )

    # ── Feedback on wake word ──────────────────────────────────

    def wake_word_callback(self, msg: String):
        self.get_logger().info(f'🔊 Wake word feedback: "{msg.data}"')

        # 1) Audio tone through speaker
        self._play_tone(
            frequencies=[800, 1200],
            durations=[0.15, 0.15],
            volume=self.wake_volume,
        )

        # 2) STM32 buzzer beep (quiet — low freq away from resonance)
        buzzer_msg = BuzzerState()
        buzzer_msg.freq = self.buzzer_freq
        buzzer_msg.on_time = self.buzzer_on_time
        buzzer_msg.off_time = 0.01
        buzzer_msg.repeat = 1
        self._buzzer_pub.publish(buzzer_msg)

        # 3) LED flash (cyan by default)
        led_msg = ColorRGBA()
        led_msg.r = self._led_r
        led_msg.g = self._led_g
        led_msg.b = self._led_b
        led_msg.a = self._led_a
        self._led_pub.publish(led_msg)

    # ── Feedback on ASR result ─────────────────────────────────

    def asr_result_callback(self, msg: String):
        self.get_logger().debug(f'ASR result feedback: "{msg.data}"')
        self._play_tone(
            frequencies=[1000],
            durations=[0.1],
            volume=self.result_volume,
        )

    # ── Audio tone helper ──────────────────────────────────────

    def _play_tone(self, frequencies, durations, volume=0.5):
        try:
            segments = []
            for freq, dur in zip(frequencies, durations):
                t = np.linspace(0, dur, int(self.sample_rate * dur), endpoint=False)
                envelope = np.ones_like(t)
                fade_len = min(int(0.02 * self.sample_rate), len(t) // 4)
                if fade_len > 0:
                    envelope[:fade_len] = np.linspace(0, 1, fade_len)
                    envelope[-fade_len:] = np.linspace(1, 0, fade_len)
                segment = np.sin(2 * np.pi * freq * t) * envelope * volume
                segments.append(segment)

            audio = np.concatenate(segments).astype(np.float32)
            sd.play(audio, samplerate=self.sample_rate,
                    device=self.device_index if self.device_index >= 0 else None)
        except Exception as e:
            self.get_logger().warning(f'Failed to play audio: {e}', throttle_duration_sec=10.0)


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
