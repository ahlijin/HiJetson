#!/usr/bin/env python3
"""
servo_tracker_node.py

Listens for wake events (/voice/wake). On wake, rotates the camera
gimbal (servo) toward the latest DOA direction.
If the sound source is beyond the servo's mechanical range (±45°),
publishes cmd_vel to rotate the whole robot to face the sound.

DOA data is read passively — rotation only happens on wake events.

Topics:
  /voice/doa_angle       (Float32, sub)      — latest DOA angle
  /voice/wake            (Bool, sub)         — wake event triggers rotation
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
  rotate_gain      (float) Rotation speed / open-loop timing (default: 0.3)
  chase_timeout    (float) Max open-loop rotate duration (default: 10.0)
"""

import time
import math
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Bool
from geometry_msgs.msg import Twist, Vector3
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
        self.chase_timeout = self.declare_parameter('chase_timeout', 10.0).value

        self._servo_pub = self.create_publisher(ServosPosition, '/servo_controller', 1)
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 1)

        # State
        self._current_pulse = float(self.center_pulse)
        self._latest_doa: float | None = None
        self._latest_valid_doa: float | None = None
        self._latest_locked_doa: float | None = None
        self._rotate_timer = None

        # Subscribers
        self.create_subscription(Float32, '/voice/doa_angle', self._doa_cb, 10)
        self.create_subscription(Float32, '/voice/doa_locked', self._locked_doa_cb, 10)
        self.create_subscription(Bool, '/voice/vad_hw', self._vad_cb, 10)
        self.create_subscription(Bool, '/voice/wake', self._wake_cb, 10)

        self.get_logger().info(
            f"ServoTracker started: servo={self.servo_pan_id}, "
            f"center={self.center_pulse}, range={self.range_pulse} "
            f"({self.angle_range}°), rotate_gain={self.rotate_gain}"
        )

    # ── DOA (passive — store latest; only trust value while voice active) ──

    def _doa_cb(self, msg: Float32):
        if msg.data >= 0:
            self._latest_doa = msg.data

    def _vad_cb(self, msg: Bool):
        # 兜底: 语音期间的方向 (优先用 VAD 上升沿锁存值)
        if msg.data and self._latest_doa is not None:
            self._latest_valid_doa = self._latest_doa

    def _locked_doa_cb(self, msg: Float32):
        # 唤醒词方向: voice_doa 在 VAD 上升沿锁存并发布
        if msg.data >= 0:
            self._latest_locked_doa = msg.data

    # ── Wake event → rotate toward sound ──────────────────────────

    def _wake_cb(self, msg: Bool):
        if not msg.data:
            # 退出 / 自动休眠: 舵机回正, 停止旋转
            self._cancel_chase()
            self._stop_rotation()
            self._publish_servo(float(self.center_pulse))
            self.get_logger().info("Sleep — servo home, rotation stopped")
            return
        doa = self._latest_locked_doa
        if doa is None:
            doa = self._latest_valid_doa  # 兜底: 语音期间方向
        if doa is None:
            self.get_logger().info(
                "No valid DOA (no voice detected yet) — skipping rotation")
            return
        self._rotate_to_doa(doa)

    # ── Core rotation logic ────────────────────────────────────────

    def _rotate_to_doa(self, doa: float):
        # Normalise: 0 = front, ±180
        if doa > 180.0:
            doa -= 360.0
        half_range = self.angle_range / 2.0

        if abs(doa) <= half_range:
            # 声源在舵机范围内: 只转舵机对准, 不转车
            self._cancel_chase()
            self._publish_servo(self._angle_to_pulse(doa))
            self._stop_rotation()
            self.get_logger().info(
                f"Wake — DOA={doa:.0f}° → servo pulse={self._current_pulse:.0f}")
            return

        # 声源超出舵机范围: 整体旋转小车闭环追踪, 直到声源进入范围
        self._start_chase(doa)

    # ── Open-loop rotate (sound beyond servo range — servo untouched) ──

    def _start_chase(self, doa: float):
        if self._rotate_timer:
            self._rotate_timer.cancel()
        # 开环整体旋转: 转 doa 的最短角 (右=+ / 左=-), 舵机不动
        rad = abs(doa) * math.pi / 180.0
        duration = min(rad / self.rotate_gain, self.chase_timeout)
        direction = -1.0 if doa > 0 else 1.0  # 右→右转(angular<0), 左→左转(angular>0)
        self._publish_rotation(direction * self.rotate_gain)
        self.get_logger().info(
            f"DOA={doa:.0f}° beyond servo range — rotating robot "
            f"{abs(doa):.0f}° ({duration:.1f}s), servo untouched")
        self._rotate_timer = self.create_timer(duration, self._stop_chase)

    def _stop_chase(self):
        self._stop_rotation()
        if self._rotate_timer:
            self._rotate_timer.cancel()
            self._rotate_timer = None
        self.get_logger().info("Rotation done — robot now faces the sound")

    def _cancel_chase(self):
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
