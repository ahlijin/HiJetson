#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D
from std_msgs.msg import Float32MultiArray, MultiArrayDimension
import numpy as np
from cv_bridge import CvBridge
from builtin_interfaces.msg import Time
import time


class DepthProcessorNode(Node):
    def __init__(self):
        super().__init__('depth_processor_node')
        self.bridge = CvBridge()
        self.latest_depth = None
        self.latest_detections = None

        self.depth_sub = self.create_subscription(Image, '/camera/depth/image_raw', self.depth_callback, 10)
        self.det_sub = self.create_subscription(Detection2DArray, '/vision/detection_result', self.det_callback, 10)
        self.dist_pub = self.create_publisher(Float32MultiArray, '/vision/distance_result', 10)
        self.get_logger().info('DepthProcessorNode started')

    def depth_callback(self, msg):
        try:
            self.latest_depth = self.bridge.imgmsg_to_cv2(msg, '32FC1')
        except Exception as e:
            self.get_logger().error(f'Depth conversion error: {e}')

    def det_callback(self, msg):
        if self.latest_depth is None:
            return
        dh, dw = self.latest_depth.shape[:2]
        distances = []
        for det in msg.detections:
            x1 = int(det.x * dw)
            y1 = int(det.y * dh)
            x2 = int((det.x + det.width) * dw)
            y2 = int((det.y + det.height) * dh)
            roi = self.latest_depth[y1:y2, x1:x2]
            valid = roi[(roi > 0) & (roi < 10.0)]
            if len(valid) > 0:
                dist = float(np.median(valid))
            else:
                dist = 0.0
            distances.append(dist)

        msg_out = Float32MultiArray()
        msg_out.layout.dim.append(MultiArrayDimension(label='detections', size=len(distances), stride=1))
        msg_out.data = distances
        self.dist_pub.publish(msg_out)

def main(args=None):
    rclpy.init(args=args)
    node = DepthProcessorNode()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally: node.destroy_node(); rclpy.shutdown()
if __name__ == '__main__': main()
