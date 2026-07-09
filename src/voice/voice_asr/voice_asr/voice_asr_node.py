#!/usr/bin/env python3
"""
voice_asr_node.py

ASR using Whisper. Always transcribes audio clips from VAD.
Wake word: "小车小车" detected in transcription → enables command mode.
When awake, parses commands and publishes to hardware topics.
Uses opencc for Traditional→Simplified conversion.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32MultiArray
from voice_msgs.msg import VoiceCommand
from ros_robot_controller_msgs.msg import BuzzerState, ServoPosition, ServosPosition
import numpy as np
import whisper
import torch
import re
from scipy.signal import butter, sosfilt
from opencc import OpenCC


class VoiceASRNode(Node):
    def __init__(self):
        super().__init__('voice_asr')
        self.model_size = self.declare_parameter('model_size', 'base').value
        self.device = self.declare_parameter('device', 'cuda').value
        self.language = self.declare_parameter('language', 'zh').value
        self.sample_rate = self.declare_parameter('sample_rate', 16000).value
        self.wake_word_timeout = self.declare_parameter('wake_word_timeout', 8.0).value

        self._awake = False
        self._awake_timer = None

        self.hp_cutoff = self.declare_parameter('hp_cutoff', 300).value
        self._init_hp_filter()
        self._cc = OpenCC("t2s")

        self.asr_pub = self.create_publisher(String, '/voice/asr_result', 10)
        self.cmd_pub = self.create_publisher(VoiceCommand, '/voice/voice_command', 10)
        self.ww_pub = self.create_publisher(String, '/voice/wake_word', 10)
        self.buzzer_pub = self.create_publisher(BuzzerState, '/ros_robot_controller/set_buzzer', 10)
        self.servo_pub = self.create_publisher(ServosPosition, '/ros_robot_controller/bus_servo/set_position', 10)

        self.sub = self.create_subscription(
            Float32MultiArray, '/voice/audio_clip', self.audio_clip_callback, 10
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

    def _wake_up(self):
        self._awake = True
        if self._awake_timer is not None:
            self._awake_timer.cancel()
        self._awake_timer = self.create_timer(self.wake_word_timeout, self._go_to_sleep)
        self.get_logger().info('Awakened - listening for %ds' % self.wake_word_timeout)
        b = BuzzerState()
        b.freq = 800
        b.on_time = 0.1
        b.off_time = 0.0
        b.repeat = 1
        self.buzzer_pub.publish(b)

    def _go_to_sleep(self):
        self._awake = False
        if self._awake_timer is not None:
            self._awake_timer.cancel()
            self._awake_timer = None
        self.get_logger().info('Timeout - going back to sleep')

    def _contains_wake_word(self, text):
        for w in ['小车小车', '小红小红', '小绿小绿', '小方小方']:
            if w in text:
                return True
        return False

    def _parse_command(self, text):
        cmd_text = re.sub(r'小车小车|小红小红|小绿小绿|小方小方', '', text).strip()
        if not cmd_text:
            return {'action': 'none'}
        if any(w in cmd_text for w in ['左转', '左拐', '左']):
            return {'action': 'servo', 'position': 2500}
        elif any(w in cmd_text for w in ['右转', '右拐', '右']):
            return {'action': 'servo', 'position': 500}
        elif any(w in cmd_text for w in ['蜂鸣', '响', '叫']):
            return {'action': 'buzzer', 'freq': 1900, 'repeat': 3}
        elif any(w in cmd_text for w in ['前进', '直走', '前']):
            return {'action': 'motor', 'direction': 'forward'}
        elif any(w in cmd_text for w in ['后退', '倒车', '后']):
            return {'action': 'motor', 'direction': 'backward'}
        elif any(w in cmd_text for w in ['停止', '停', '刹车']):
            return {'action': 'motor', 'direction': 'stop'}
        else:
            return {'action': 'unknown', 'text': cmd_text}

    def _execute_command(self, cmd):
        action = cmd.get('action')
        self.get_logger().info('Executing: %s' % str(cmd))
        if action == 'servo':
            msg = ServosPosition()
            msg.duration = 0.3
            msg.position_unit = 'pulse'
            s = ServoPosition()
            s.id = 1
            s.position = float(cmd['position'])
            msg.position = [s]
            self.servo_pub.publish(msg)
        elif action == 'buzzer':
            msg = BuzzerState()
            msg.freq = cmd.get('freq', 1900)
            msg.on_time = 0.15
            msg.off_time = 0.1
            msg.repeat = cmd.get('repeat', 2)
            self.buzzer_pub.publish(msg)
        elif action in ('motor', 'unknown'):
            self.get_logger().info('%s not yet wired' % action)

    def _preprocess_audio(self, audio):
        filtered = sosfilt(self._hp_sos, audio).astype(np.float32)
        rms = np.sqrt(np.mean(filtered ** 2))
        if rms > 1e-6:
            filtered = filtered * (0.08 / rms)
        return np.clip(filtered, -1.0, 1.0)

    def audio_clip_callback(self, msg):
        if self.model is None:
            return
        audio = np.array(msg.data, dtype=np.float32)
        if len(audio) == 0:
            return
        raw_rms = np.sqrt(np.mean(audio ** 2))
        if raw_rms < 0.005:
            return

        self.get_logger().info('Clip: %.2fs RMS=%.4f' % (len(audio)/self.sample_rate, raw_rms))
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

            # Always publish raw result
            text_msg = String()
            text_msg.data = full_text
            self.asr_pub.publish(text_msg)

            # Wake word check
            if self._contains_wake_word(full_text):
                if not self._awake:
                    self._wake_up()
                    ww = String()
                    ww.data = '小车小车'
                    self.ww_pub.publish(ww)
                # Parse any command after wake word
                cmd = self._parse_command(full_text)
                if cmd['action'] != 'none':
                    self._execute_command(cmd)
            elif self._awake:
                # Awake — full text is the command
                cmd = self._parse_command(full_text)
                if cmd['action'] not in ('none', 'unknown'):
                    self._execute_command(cmd)
                    # Reset wake timer on valid command
                    if self._awake_timer is not None:
                        self._awake_timer.cancel()
                    self._awake_timer = self.create_timer(self.wake_word_timeout, self._go_to_sleep)

            # Publish structured command
            cmd_msg = VoiceCommand()
            cmd_msg.command_text = full_text
            cmd_msg.confidence = float(result.get('confidence', 1.0) or 1.0)
            cmd_msg.timestamp = self.get_clock().now().to_msg()
            self.cmd_pub.publish(cmd_msg)

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
