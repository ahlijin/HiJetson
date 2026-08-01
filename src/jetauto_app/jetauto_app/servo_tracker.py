#!/usr/bin/env python3
"""
servo_tracker_node.py

Listens for voice commands (/voice/voice_command). On receiving a command,
rotates the camera gimbal (servo) toward the latest DOA direction.
If the sound source is beyond the servo's mechanical range (±45°),
publishes cmd_vel to rotate the whole robot to face the sound.

DOA data is read passively — rotation only happens on voice command.

Topics:
  /voice/doa_angle       (Float32, sub)      — latest DOA angle
  /voice/voice_command   (VoiceCommand, sub) — triggers rotation
  /servo_controller      (ServosPosition, pub) — gimbal servo
  /cmd_vel               (Twist, pub)        — robot rotation

Parameters (~servo_tracker):
  servo_pan_id     (int)   Pan servo ID           (default: 1)
  center_pulse     (int)   Center position         (default: 500)
  range_pulse      (int)   Max deviation from centre (default: 188)
  angle_range      (float) DOA range mapped to full servo range (default: 90.0)
  invert           (bool)  Reverse servo direction (default: false)
  pulse_min        (int)   Hard lower pulse limit  (default: 312)
  pulse_max        (int)   Hard upper pulse limit  (default: 688)
  rotate_gain      (float) Rotation speed (default: 0.3)
  rotate_duration  (float) Seconds to rotate before re-checking (default: 0.5)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from geometry_msgs.msg import Twist, Vector3
from voice_msgs.msg import VoiceCommand
from ros_robot_controller_msgs.msg import ServosPosition, ServoPosition


class ServoTrackerNode(Node):
    def __init__(self):
        super().__init__('servo_tracker')

        self.servo_pan_id = self.declare_parameter('servo_pan_id', 1).value
        self.center_pulse = self.declare_parameter('center_pulse', 500).value
        self.range_pulse = self.declare_parameter('range_pulse', 188).value
        self.angle_range = self.declare_parameter('angle_range', 90.0).value
        self.invert = self.declare_parameter('invert', False).value
        self.pulse_min = self.declare_parameter('pulse_min', 312).value
        self.pulse_max = self.declare_parameter('pulse_max', 688).value
        self.rotate_gain = self.declare_parameter('rotate_gain', 0.3).value
        self.rotate_duration = self.declare_parameter('rotate_duration', 0.5).value

        self._servo_pub = self.create_publisher(ServosPosition, '/servo_controller', 1)
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 1)

        # State
        self._current_pulse = float(self.center_pulse)
        self._latest_doa: float | None = None
        self._rotate_timer = None

        # Subscribers
        self.create_subscription(Float32, '/voice/doa_angle', self._doa_cb, 10)
        self.create_subscription(VoiceCommand, '/voice/voice_command', self._cmd_cb, 10)

        self.get_logger().info(
            f"ServoTracker started: servo={self.servo_pan_id}, "
            f"center={self.center_pulse}, range={self.range_pulse} "
            f"({self.angle_range}°), rotate_gain={self.rotate_gain}"
        )

    # ── DOA (passive — just store latest) ──────────────────────────

    def _doa_cb(self, msg: Float32):
        if msg.data >= 0:
            self._latest_doa = msg.data

    # ── Voice command → rotate ─────────────────────────────────────

    def _cmd_cb(self, msg: VoiceCommand):
        if self._latest_doa is None:
            self.get_logger().info("No DOA data yet — skipping rotation")
            return
        self._rotate_to_doa(self._latest_doa)

    # ── Core rotation logic ────────────────────────────────────────

    def _rotate_to_doa(self, doa: float):
        # Normalise: 0 = front, ±180
        if doa > 180.0:
            doa -= 360.0
        half_range = self.angle_range / 2.0
        abs_doa = abs(doa)

        # Step 1: Move servo
        pulse = self._angle_to_pulse(doa)
        min_p = self.center_pulse - self.range_pulse
        max_p = self.center_pulse + self.range_pulse
        clamped = max(min_p, min(max_p, pulse))
        self._publish_servo(clamped)
        self.get_logger().info(
            f"Voice cmd — DOA={doa:.0f}° → servo pulse={clamped:.0f}")

        # Step 2: If servo saturated AND sound outside range, rotate robot
        margin = 0.05 * self.range_pulse
        at_limit = (clamped <= min_p + margin or clamped >= max_p - margin)
        if at_limit and abs_doa > half_range:
            direction = 1.0 if doa > 0 else -1.0
            speed = direction * self.rotate_gain
            self._publish_rotation(speed)
            self.get_logger().info(
                f"Servo saturated — rotating robot: angular_z={speed:.2f}")
            # Schedule stop
            if self._rotate_timer:
                self._rotate_timer.cancel()
            self._rotate_timer = self.create_timer(
                self.rotate_duration, self._stop_rotate)
        else:
            self._stop_rotation()

    def _stop_rotate(self):
        self._stop_rotation()
        if self._rotate_timer:
            self._rotate_timer.cancel()
            self._rotate_timer = None

    # ── Helpers ────────────────────────────────────────────────────

    def _angle_to_pulse(self, angle_deg: float) -> float:
        half_range = self.angle_range / 2.0
        clamped = max(-half_range, min(half_range, angle_deg))
        norm = clamped / half_range
        if self.invert:
            norm = -norm
        return self.center_pulse + norm * self.range_pulse

    def _publish_servo(self, pulse: float):
        # 硬件硬限幅:总线舵机物理范围 [312, 688] (±45°),防止越界撞限位
        pulse = max(float(self.pulse_min), min(float(self.pulse_max), pulse))
        msg = ServosPosition()
        msg.duration = 0.15
        msg.position_unit = 'pulse'
        s = ServoPosition()
        s.id = self.servo_pan_id
        s.position = float(pulse)
        msg.position = [s]
        self._servo_pub.publish(msg)
        self._current_pulse = float(pulse)

    def _publish_rotation(self, az: float):
        self._cmd_vel_pub.publish(Twist(angular=Vector3(x=0.0, y=0.0, z=az)))

    def _stop_rotation(self):
        self._publish_rotation(0.0)


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
