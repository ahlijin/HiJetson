#!/usr/bin/env python3
"""
voice_asr_node.py

Automatic Speech Recognition using OpenAI Whisper (PyTorch CUDA).
Subscribes to /voice/audio_clip (Float32MultiArray) from the VAD node,
transcribes the audio, and publishes the recognized text.

Publishes:
  /voice/asr_result (std_msgs/String) - Recognized text string
  /voice/voice_command (voice_msgs/VoiceCommand) - Structured voice command
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32MultiArray
from voice_msgs.msg import VoiceCommand
import numpy as np
import whisper
import torch
from scipy.signal import butter, sosfilt


class VoiceASRNode(Node):
    def __init__(self):
        super().__init__('voice_asr')

        # Parameters
        self.model_size = self.declare_parameter('model_size', 'base').value
        self.device = self.declare_parameter('device', 'cuda').value
        self.language = self.declare_parameter('language', 'zh').value
        self.sample_rate = self.declare_parameter('sample_rate', 16000).value

        # ── Wake word gating ────────────────────────────────────────
        self.wake_word_enabled = self.declare_parameter('wake_word_enabled', True).value
        self.wake_word_timeout = self.declare_parameter('wake_word_timeout', 5.0).value
        self._awake = not self.wake_word_enabled  # if disabled, always awake
        self._awake_timer = None

        # High-pass filter: 去除 139Hz Jetson 风扇噪声
        self.hp_cutoff = self.declare_parameter('hp_cutoff', 300).value
        self._init_hp_filter()

        # Publishers
        self.asr_pub = self.create_publisher(String, '/voice/asr_result', 10)
        self.cmd_pub = self.create_publisher(VoiceCommand, '/voice/voice_command', 10)

        # Subscriber to audio clips from VAD
        self.sub = self.create_subscription(
            Float32MultiArray, '/voice/audio_clip', self.audio_clip_callback, 10
        )

        # Subscriber to wake word trigger (only if enabled)
        if self.wake_word_enabled:
            self._ww_sub = self.create_subscription(
                String, '/voice/wake_word', self.wake_word_callback, 10
            )
            self.get_logger().info(
                f'Wake word gating enabled: timeout={self.wake_word_timeout}s'
            )

        # Load Whisper model
        self.get_logger().info(
            f'Loading whisper model: {self.model_size} (device={self.device})'
        )
        try:
            self.model = whisper.load_model(self.model_size, device=self.device)
            self.get_logger().info('Whisper model loaded successfully')
        except Exception as e:
            self.get_logger().error(f'Failed to load Whisper model: {e}')
            self.model = None

    def _init_hp_filter(self):
        """初始化高通滤波器（Butterworth 4阶），去除风扇等低频噪声。"""
        self._hp_sos = butter(4, self.hp_cutoff, btype='high', fs=self.sample_rate, output='sos')
        self.get_logger().info(f'High-pass filter initialized: cutoff={self.hp_cutoff}Hz')

    # ── Wake word handling ─────────────────────────────────────────

    def wake_word_callback(self, msg: String):
        """Wake word detected — stay awake for wake_word_timeout seconds."""
        self._awake = True
        # Cancel any existing timer
        if self._awake_timer is not None:
            self._awake_timer.cancel()
        # Set one-shot timer to go back to sleep
        self._awake_timer = self.create_timer(self.wake_word_timeout, self._go_to_sleep)

        self.get_logger().info(
            f'Wake word received: "{msg.data}" — '
            f'listening for {self.wake_word_timeout}s'
        )

    def _go_to_sleep(self):
        self._awake = False
        if self._awake_timer is not None:
            self._awake_timer.cancel()
            self._awake_timer = None
        self.get_logger().info('Wake word timeout — going back to sleep')

    def _preprocess_audio(self, audio: np.ndarray) -> np.ndarray:
        """预处理音频：高通滤波 + RMS归一化。"""
        # 1. 高通滤波去除低频噪声（风扇/空调）
        filtered = sosfilt(self._hp_sos, audio).astype(np.float32)

        # 2. RMS归一化到目标电平
        rms = np.sqrt(np.mean(filtered ** 2))
        target_rms = 0.08  # 目标 RMS 电平
        if rms > 1e-6:
            filtered = filtered * (target_rms / rms)

        # 裁剪防止削波
        return np.clip(filtered, -1.0, 1.0)

    def audio_clip_callback(self, msg: Float32MultiArray):
        """Process an audio clip when VAD detects a complete speech segment."""
        if self.model is None:
            self.get_logger().warning('Whisper model not loaded, skipping')
            return

        # ── Wake word gate ─────────────────────────────────────────
        if not self._awake:
            self.get_logger().debug('Ignoring audio clip — not awake (say wake word first)')
            return

        # Convert Float32MultiArray to numpy array
        audio = np.array(msg.data, dtype=np.float32)

        if len(audio) == 0:
            self.get_logger().warning('Received empty audio clip')
            return

        duration = len(audio) / self.sample_rate
        self.get_logger().info(
            f'Processing audio clip: {len(audio)} samples ({duration:.2f}s)'
        )

        # 预处理：高通滤波 + 归一化
        audio = self._preprocess_audio(audio)

        # Run inference
        try:
            result = self.model.transcribe(
                audio,
                language=self.language,
                fp16=torch.cuda.is_available(),
                verbose=False,
            )

            full_text = result.get('text', '').strip()

            if not full_text:
                self.get_logger().info('No speech detected in audio clip')
                return

            self.get_logger().info(
                f'Recognized: "{full_text}" (language={result.get("language", "unknown")})'
            )

            # Publish as string result
            text_msg = String()
            text_msg.data = full_text
            self.asr_pub.publish(text_msg)

            # Publish as structured VoiceCommand
            cmd_msg = VoiceCommand()
            cmd_msg.command_text = full_text
            cmd_msg.confidence = float(result.get('confidence', 1.0) if result.get('confidence') else 1.0)
            cmd_msg.timestamp = self.get_clock().now().to_msg()
            self.cmd_pub.publish(cmd_msg)

        except Exception as e:
            self.get_logger().error(f'ASR inference failed: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = VoiceASRNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
