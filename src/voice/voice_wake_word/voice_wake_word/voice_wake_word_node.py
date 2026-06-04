#!/usr/bin/env python3
"""
voice_wake_word_node.py

Wake word detection using OpenWakeWord.
Subscribes to /voice/audio_raw (Float32MultiArray), runs streaming wake word
detection, and publishes /voice/wake_word (std_msgs/String) on detection.

Configuration (from voice_params.yaml):
  ~model_name (str) — OpenWakeWord pretrained model name
    (e.g. 'hey_jarvis', 'alexa', 'hey_mycroft', 'hey_rhasspy')
  ~threshold (float) — Detection threshold (0.0–1.0, default 0.5)
  ~cooldown (float) — Seconds to wait between wake word triggers (default 3.0)
  ~sample_rate (int) — Audio sample rate (default 16000)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32MultiArray, Bool
import numpy as np
import os


class VoiceWakeWordNode(Node):
    def __init__(self):
        super().__init__('voice_wake_word')

        # ── Parameters ──────────────────────────────────────────────
        self.model_name = self.declare_parameter('model_name', 'hey_jarvis').value
        self.threshold = self.declare_parameter('threshold', 0.5).value
        self.cooldown = self.declare_parameter('cooldown', 3.0).value
        self.sample_rate = self.declare_parameter('sample_rate', 16000).value

        # ── OpenWakeWord model ──────────────────────────────────────
        self._model = None
        self._load_model()

        # ── State ───────────────────────────────────────────────────
        self._last_trigger_time = 0.0
        self._vad_active = True  # Default to True for backward compat

        # ── Publisher / Subscriber ──────────────────────────────────
        self.pub = self.create_publisher(String, '/voice/wake_word', 10)
        self.sub = self.create_subscription(
            Float32MultiArray, '/voice/audio_raw', self.audio_callback, 10
        )
        # VAD gate: only run wake word inference when VAD detects speech
        self._vad_sub = self.create_subscription(
            Bool, '/voice/voice_activity', self.vad_callback, 10
        )

        self.get_logger().info(
            f'VoiceWakeWordNode started: model={self.model_name}, '
            f'threshold={self.threshold}, cooldown={self.cooldown}s'
        )

    def _load_model(self):
        """Load the OpenWakeWord Model with the configured wake word."""
        try:
            from openwakeword import Model
            import openwakeword

            # Resolve model path — try string name first (looks up pretrained),
            # then fall back to full path in resources
            models_dir = os.path.join(
                os.path.dirname(openwakeword.__file__),
                'resources', 'models'
            )

            # Check if a matching model file exists
            model_path = None
            for f in os.listdir(models_dir):
                if f.endswith('.tflite') and self.model_name in f:
                    model_path = os.path.join(models_dir, f)
                    break

            if model_path and os.path.exists(model_path):
                self._model = Model(
                    wakeword_models=[model_path],
                    enable_speex_noise_suppression=False,
                    ncpu=2,
                )
                self._model_name_key = list(self._model.models.keys())[0]
                self.get_logger().info(f'Loaded model: {self._model_name_key}')
            else:
                # Fall back to pretrained name resolution
                self._model = Model(
                    wakeword_models=[self.model_name],
                    enable_speex_noise_suppression=False,
                    ncpu=2,
                )
                self._model_name_key = list(self._model.models.keys())[0]
                self.get_logger().info(f'Loaded pretrained model: {self._model_name_key}')

        except Exception as e:
            self.get_logger().error(f'Failed to load OpenWakeWord model: {e}')
            self._model = None

    def vad_callback(self, msg: Bool):
        """VAD activity gate — only run wake word inference when speech is active."""
        self._vad_active = msg.data

    def audio_callback(self, msg: Float32MultiArray):
        # VAD gate: skip inference when no speech activity
        if not self._vad_active:
            return

        if self._model is None:
            return

        # Convert Float32MultiArray → numpy int16
        audio_f32 = np.array(msg.data, dtype=np.float32)
        audio_int16 = np.clip(audio_f32 * 32767, -32768, 32767).astype(np.int16)

        if len(audio_int16) < 128:  # too short
            return

        # Run prediction
        try:
            predictions = self._model.predict(audio_int16)
        except Exception as e:
            self.get_logger().warning(f'Predict failed: {e}', throttle_duration_sec=10.0)
            return

        score = predictions.get(self._model_name_key, 0.0)

        # Debounce: only trigger if cooldown has elapsed
        now = self.get_clock().now().nanoseconds / 1e9
        if score >= self.threshold and (now - self._last_trigger_time) >= self.cooldown:
            self._last_trigger_time = now
            msg_out = String()
            msg_out.data = self.model_name
            self.pub.publish(msg_out)
            duration = len(audio_int16) / self.sample_rate
            self.get_logger().info(
                f'WAKE WORD DETECTED: {self.model_name} '
                f'(score={score:.3f}, frame={duration*1000:.0f}ms)'
            )

    def destroy_node(self):
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceWakeWordNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
