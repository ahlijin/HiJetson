#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from voice_msgs.msg import VoiceCommand
from vision_msgs.msg import Detection2DArray
from std_msgs.msg import Float32MultiArray
from fusion_msgs.msg import FusedResult
from builtin_interfaces.msg import Time
import time
import re


class FusionNode(Node):
    def __init__(self):
        super().__init__('fusion_node')
        self.latest_detections = []
        self.latest_distances = []

        self.voice_sub = self.create_subscription(VoiceCommand, '/voice/voice_command', self.voice_callback, 10)
        self.det_sub = self.create_subscription(Detection2DArray, '/vision/detection_result', self.det_callback, 10)
        self.dist_sub = self.create_subscription(Float32MultiArray, '/vision/distance_result', self.dist_callback, 10)
        self.fusion_pub = self.create_publisher(FusedResult, '/fusion/result', 10)
        self.get_logger().info('FusionNode started')

    def det_callback(self, msg):
        self.latest_detections = [(d.label, d.confidence) for d in msg.detections]

    def dist_callback(self, msg):
        self.latest_distances = msg.data

    def voice_callback(self, msg):
        intent = self._parse_intent(msg.command_text)
        objects = [d[0] for d in self.latest_detections]

        result = FusedResult()
        result.detected_objects = objects
        result.distances = self.latest_distances
        result.voice_command = msg.command_text
        result.intent = intent
        now = time.time()
        ts = Time()
        ts.sec = int(now)
        ts.nanosec = int((now - int(now)) * 1e9)
        result.timestamp = ts
        self.fusion_pub.publish(result)
        self.get_logger().info(f'Fusion: intent="{intent}", cmd="{msg.command_text}"')

    def _parse_intent(self, text):
        """Simple Chinese NLP intent parser."""
        if not text:
            return 'unknown'
        if re.search(r'??|???|????|????', text):
            return 'query_scene'
        if re.search(r'??(?|?)|??|??|??', text):
            return 'query_object_location'
        if re.search(r'?|?|?|?|??|??', text):
            return 'grasp_object'
        if re.search(r'??|????|???|???', text):
            return 'come_here'
        if re.search(r'??|??|??|??', text):
            return 'go_away'
        if re.search(r'??|?|??|??', text):
            return 'stop'
        return 'unknown'

def main(args=None):
    rclpy.init(args=args)
    node = FusionNode()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally: node.destroy_node(); rclpy.shutdown()
if __name__ == '__main__': main()
