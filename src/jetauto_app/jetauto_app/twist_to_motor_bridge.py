#!/usr/bin/env python3
"""Twist → MotorsState bridge for Jetson's ros_robot_controller.

Subscribes to /cmd_vel (Twist), converts to MotorsState using mecanum kinematics,
and publishes to /ros_robot_controller/set_motor.
"""

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from ros_robot_controller_msgs.msg import MotorState, MotorsState


class TwistToMotorBridge(Node):
    def __init__(self):
        super().__init__('twist_to_motor')

        self.declare_parameter('wheelbase', 0.216)
        self.declare_parameter('track_width', 0.195)
        self.declare_parameter('wheel_diameter', 0.097)
        self.declare_parameter('motor_ids', [1, 2, 3, 4])

        self._wheelbase = self.get_parameter('wheelbase').value
        self._track_width = self.get_parameter('track_width').value
        self._wheel_diameter = self.get_parameter('wheel_diameter').value
        self._motor_ids = self.get_parameter('motor_ids').value

        self._sub = self.create_subscription(Twist, '/cmd_vel', self._cb, 10)
        self._pub = self.create_publisher(
            MotorsState, '/ros_robot_controller/set_motor', 10)

        self.get_logger().info(
            f'TwistToMotorBridge started: '
            f'wheelbase={self._wheelbase} track={self._track_width} '
            f'diameter={self._wheel_diameter} motors={self._motor_ids}')

    def _speed_to_rps(self, speed: float) -> float:
        """Convert m/s to rotations per second."""
        return speed / (math.pi * self._wheel_diameter)

    def _cb(self, msg: Twist) -> None:
        """Twist → 四轮 rps (mecanum 逆运动学, 同 Pi3 mecanum.py 公式)."""
        lx = msg.linear.x
        ly = msg.linear.y
        az = msg.angular.z
        half = (self._wheelbase + self._track_width) / 2.0

        motor1 = lx - ly - az * half
        motor2 = lx + ly - az * half
        motor3 = lx + ly + az * half
        motor4 = lx - ly + az * half

        speeds = [self._speed_to_rps(v) for v in [motor1, motor2, -motor3, -motor4]]

        states = MotorsState()
        for i, rps in enumerate(speeds):
            m = MotorState()
            m.id = self._motor_ids[i]
            m.rps = float(rps)
            states.data.append(m)

        self._pub.publish(states)


def main(args=None):
    rclpy.init(args=args)
    node = TwistToMotorBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
