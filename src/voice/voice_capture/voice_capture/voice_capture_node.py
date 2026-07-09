#!/usr/bin/env python3
"""
voice_capture_node.py

Captures audio via sounddevice (ALSA direct) and publishes raw frames to /voice/audio_raw.
Auto-detects ReSpeaker by name. No software gain — matches the working standalone script.
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, MultiArrayDimension
import sounddevice as sd
import numpy as np


class VoiceCaptureNode(Node):
    def __init__(self):
        super().__init__('voice_capture')

        self.sample_rate = self.declare_parameter('sample_rate', 16000).value
        self.frame_size = self.declare_parameter('frame_size', 1600).value
        self.channels = self.declare_parameter('channels', 1).value

        self.publisher_ = self.create_publisher(Float32MultiArray, '/voice/audio_raw', 10)
        self.buffer = np.zeros((0,), dtype=np.float32)

        # Auto-detect ReSpeaker by name (same as standalone script)
        device_idx = self._find_respeaker()
        if device_idx is None:
            self.get_logger().error('ReSpeaker not found!')
            self.stream = None
            return

        # ALSA direct (same as continuous script)
        self.get_logger().info(
            f'VoiceCaptureNode started: {self.sample_rate}Hz, '
            f'{self.frame_size} samples/frame, device={device_idx} (ALSA direct)'
        )

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.frame_size,
                device=device_idx,
                dtype='float32',
                callback=self.audio_callback,
            )
            self.stream.start()
            self.get_logger().info('Audio stream started successfully')
        except Exception as e:
            self.get_logger().error(f'Failed to start audio stream: {e}')
            self.stream = None

    def _find_respeaker(self) -> int | None:
        for i, d in enumerate(sd.query_devices()):
            name = d['name']
            if ('ArrayUAC10' in name or 'ReSpeaker' in name) and 'hw:' in name:
                return i
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0 and ('ArrayUAC10' in d['name'] or 'ReSpeaker' in d['name']):
                return i
        return None

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            self.get_logger().warning(f'Audio status: {status}')
        audio = indata[:, 0] if indata.shape[1] > 1 else indata.flatten().astype(np.float32)
        msg = Float32MultiArray()
        msg.layout.dim.append(MultiArrayDimension(label='samples', size=len(audio), stride=1))
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
