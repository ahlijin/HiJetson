#!/usr/bin/env python3
"""
voice_asr_node.py

Pure Whisper transcriber. Listens for audio on /voice/audio_for_asr,
gated by /voice/wake (Bool). Transcribes, converts Traditional→Simplified
via opencc, and publishes the result on /voice/asr_result.

High-pass filter removes low-frequency noise before inference.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32MultiArray, Bool
import numpy as np
import whisper
import torch
from scipy.signal import butter, sosfilt
from opencc import OpenCC


class VoiceASRNode(Node):
    def __init__(self):
        super().__init__('voice_asr')
        self.model_size = self.declare_parameter('model_size', 'base').value
        self.device = self.declare_parameter('device', 'cuda').value
        self.language = self.declare_parameter('language', 'zh').value
        self.sample_rate = self.declare_parameter('sample_rate', 16000).value
        self.hp_cutoff = self.declare_parameter('hp_cutoff', 300).value

        self._awake = False

        self._init_hp_filter()
        self._cc = OpenCC("t2s")

        self.asr_pub = self.create_publisher(String, '/voice/asr_result', 10)

        self.sub = self.create_subscription(
            Float32MultiArray, '/voice/audio_for_asr', self.audio_clip_callback, 10
        )
        self.wake_sub = self.create_subscription(
            Bool, '/voice/wake', self.wake_callback, 10
        )

        self.get_logger().info('Loading whisper model: %s (device=%s)' % (self.model_size, self.device))
        try:
            self.model = whisper.load_model(self.model_size, device=self.device)
            self.get_logger().info('Whisper model loaded successfully')
        except Exception as e:
            self.get_logger().error('Failed to load Whisper model: %s' % e)
            self.model = None

    def _init_hp_filter(self):
        self._hp_sos = butter(4, self.hp_cutoff, btype='high', fs=self.sample_rate, output='sos')
        self.get_logger().info('High-pass filter initialized: cutoff=%dHz' % self.hp_cutoff)

    def wake_callback(self, msg):
        self._awake = msg.data
        self.get_logger().debug('Wake state: %s' % self._awake)

    def _preprocess_audio(self, audio):
        filtered = sosfilt(self._hp_sos, audio).astype(np.float32)
        rms = np.sqrt(np.mean(filtered ** 2))
        if rms > 1e-6:
            filtered = filtered * (0.08 / rms)
        return np.clip(filtered, -1.0, 1.0)

    def audio_clip_callback(self, msg):
        if self.model is None:
            return
        if not self._awake:
            return

        audio = np.array(msg.data, dtype=np.float32)
        if len(audio) == 0:
            return
        raw_rms = np.sqrt(np.mean(audio ** 2))
        if raw_rms < 0.005:
            return

        self.get_logger().info('Clip: %.2fs RMS=%.4f' % (len(audio) / self.sample_rate, raw_rms))
        audio = self._preprocess_audio(audio)
        try:
            result = self.model.transcribe(
                audio, language=self.language,
                fp16=torch.cuda.is_available(), verbose=False,
            )
            full_text = result.get('text', '').strip()
            if not full_text:
                return

            # 繁转简
            full_text = self._cc.convert(full_text)
            self.get_logger().info('Recognized: "%s"' % full_text)

            text_msg = String()
            text_msg.data = full_text
            self.asr_pub.publish(text_msg)

        except Exception as e:
            self.get_logger().error('ASR failed: %s' % e)


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
