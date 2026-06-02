#!/usr/bin/env python3
"""
voice_capture_node.py

Captures audio from the Astra Pro microphone via sounddevice.
Publishes raw audio frames to /voice/audio_raw as std_msgs/Float32MultiArray.

Configuration:
  ~sample_rate (int): Sample rate in Hz (default: 16000)
  ~frame_size (int): Samples per frame (default: 1600)  # 100ms at 16kHz
  ~device_index (int): ALSA/PulseAudio device index (-1 = default)
  ~channels (int): Number of input channels (default: 1, set 2 for stereo devices like ASTRA Pro)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, MultiArrayDimension
import sounddevice as sd
import numpy as np
from scipy.signal import butter, sosfilt


class VoiceCaptureNode(Node):
    def __init__(self):
        super().__init__('voice_capture')

        self.sample_rate = self.declare_parameter('sample_rate', 16000).value
        self.frame_size = self.declare_parameter('frame_size', 1600).value
        self.device_index = self.declare_parameter('device_index', -1).value
        self.channels = self.declare_parameter('channels', 1).value

        self.publisher_ = self.create_publisher(Float32MultiArray, '/voice/audio_raw', 10)
        self.buffer = np.zeros((0,), dtype=np.float32)

        # 高通滤波器：去除 Jetson 风扇低频噪声 (139Hz)
        self.hp_cutoff = self.declare_parameter('hp_cutoff', 300).value
        self._hp_sos = butter(4, self.hp_cutoff, btype='high', fs=self.sample_rate, output='sos')

        device = None if self.device_index < 0 else self.device_index

        self.get_logger().info(
            f'VoiceCaptureNode started: {self.sample_rate}Hz, '
            f'{self.frame_size} samples/frame, device={device}, ch={self.channels}'
        )

        # Start audio stream
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.frame_size,
                device=device,
                dtype='float32',
                callback=self.audio_callback,
            )
            self.stream.start()
            self.get_logger().info('Audio stream started successfully')
        except Exception as e:
            self.get_logger().error(f'Failed to start audio stream: {e}')
            self.stream = None

    def audio_callback(self, indata: np.ndarray, frames, time_info, status):
        """Called by sounddevice for each audio block."""
        if status:
            self.get_logger().warning(f'Audio status: {status}')

        # If multi-channel, mix down to mono
        if indata.shape[1] > 1:
            audio = indata.mean(axis=1).astype(np.float32)
        else:
            audio = indata.flatten().astype(np.float32)

        # 高通滤波去除 Jetson 风扇低频噪声
        audio = sosfilt(self._hp_sos, audio).astype(np.float32)

        msg = Float32MultiArray()
        msg.layout.dim.append(MultiArrayDimension(
            label='samples', size=len(audio), stride=1
        ))
        msg.data = audio.tolist()
        self.publisher_.publish(msg)

    def destroy_node(self):
        if hasattr(self, 'stream') and self.stream is not None:
            self.stream.stop()
            self.stream.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceCaptureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
