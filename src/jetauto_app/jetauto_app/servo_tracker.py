#!/usr/bin/env python3
"""
servo_tracker_node.py

Subscribes to DOA angle (/voice/doa_angle) and drives the camera gimbal
pan servo to face the sound source. Regresses to center when no DOA
is reported for a configurable timeout.

Servo mapping:
  - Servo ID 1 = pan (horizontal)
  - Position range: 500 (left) ~ 2500 (right), center ~ 1500
  - DOA 0° = front (center), positive = clockwise

Topics:
  /voice/doa_angle      (std_msgs/Float32, sub)  — DOA angle or -1 if none
  /servo_controller     (ServosPosition, pub)    — gimbal servo command

Parameters (~servo_tracker):
  servo_pan_id     (int)   Pan servo ID  (default: 1)
  center_pulse     (int)   Center position in pulses (default: 1500)
  range_pulse      (int)   Max deviation from center (default: 1000)
  angle_range      (float) DOA range that maps to full servo range°\n                           (default: 90.0 — ±45° from front)
  invert           (bool)  Reverse servo direction (default: false)
  center_timeout   (float) Seconds without DOA before centering (default: 2.0)
  rate             (float) Control loop rate in Hz (default: 20.0)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from ros_robot_controller_msgs.msg import ServosPosition, ServoPosition


class ServoTrackerNode(Node):
    def __init__(self):
        super().__init__('servo_tracker')

        self.servo_pan_id = self.declare_parameter('servo_pan_id', 1).value
        self.center_pulse = self.declare_parameter('center_pulse', 1500).value
        self.range_pulse = self.declare_parameter('range_pulse', 1000).value
        self.angle_range = self.declare_parameter('angle_range', 90.0).value
        self.invert = self.declare_parameter('invert', False).value
        self.center_timeout = self.declare_parameter('center_timeout', 2.0).value
        self.rate_hz = self.declare_parameter('rate', 20.0).value

        self._servo_pub = self.create_publisher(ServosPosition, '/servo_controller', 1)

        # State
        self._target_angle: float | None = None  # None = go to center
        self._last_doa_time = 0.0
        self._current_pulse = float(self.center_pulse)

        # Subscriber
        self._doa_sub = self.create_subscription(
            Float32, '/voice/doa_angle', self._doa_callback, 10
        )

        # Timer
        self._timer = self.create_timer(1.0 / self.rate_hz, self._control_loop)

        self.get_logger().info(
            f"ServoTracker started: servo={self.servo_pan_id}, "
            f"center={self.center_pulse}, range={self.range_pulse} ({self.angle_range}°), "
            f"timeout={self.center_timeout}s"
        )

    def _doa_callback(self, msg: Float32):
        if msg.data < 0:
            self._target_angle = None
        else:
            self._target_angle = msg.data
            self._last_doa_time = self.get_clock().now().nanoseconds / 1e9

    def _angle_to_pulse(self, angle_deg: float) -> float:
        """Map DOA angle to servo pulse width."""
        # angle 0 = center, positive = clockwise (right)
        half_range = self.angle_range / 2.0
        # Clamp to ±half_range
        clamped = max(-half_range, min(half_range, angle_deg))
        # Normalize to [-1, 1]
        norm = clamped / half_range
        if self.invert:
            norm = -norm
        return self.center_pulse + norm * self.range_pulse

    def _publish_servo(self, pulse: float):
        msg = ServosPosition()
        msg.duration = 0.15  # smooth movement
        msg.position_unit = 'pulse'
        servo = ServoPosition()
        servo.id = self.servo_pan_id
        servo.position = int(round(pulse))
        msg.position = [servo]
        self._servo_pub.publish(msg)
        self._current_pulse = float(pulse)

    def _control_loop(self):
        now = self.get_clock().now().nanoseconds / 1e9

        # No DOA or stale → center
        if self._target_angle is None or \
           (now - self._last_doa_time) > self.center_timeout:
            if abs(self._current_pulse - self.center_pulse) > 1.0:
                self._publish_servo(self.center_pulse)
                self.get_logger().info(f"ServoTracker: centering (no DOA)")
            self._target_angle = None
            return

        # Compute target pulse
        pulse = self._angle_to_pulse(self._target_angle)
        pulse = max(float(self.center_pulse - self.range_pulse),
                    min(float(self.center_pulse + self.range_pulse), pulse))

        # Skip small changes (< 5 pulses) to avoid jitter
        if abs(pulse - self._current_pulse) > 5.0:
            self._publish_servo(pulse)
            self.get_logger().info(
                f"ServoTracker: DOA={self._target_angle:.0f}° → pulse={pulse:.0f}",
                throttle_duration_sec=1.0,
            )


def main(args=None):
    rclpy.init(args=args)
    node = ServoTrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
