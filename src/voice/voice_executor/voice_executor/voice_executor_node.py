#!/usr/bin/env python3
"""
voice_executor_node.py

Executes voice commands from /voice/voice_command.
Maps phrases to motor/servo/buzzer/led actions.

Motor commands → Twist on /cmd_vel
Servo commands → ServosPosition on /servo_controller
Buzzer       → BuzzerState on /ros_robot_controller/set_buzzer
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import ColorRGBA
from geometry_msgs.msg import Twist, Vector3
from voice_msgs.msg import VoiceCommand
from ros_robot_controller_msgs.msg import (
    ServosPosition, ServoPosition, BuzzerState
)

# ── Command mapping ────────────────────────────────────────────────
MOTOR_CMD = {
    "前进":   Twist(linear=Vector3(x=0.2, y=0.0, z=0.0)),
    "向前":   Twist(linear=Vector3(x=0.2, y=0.0, z=0.0)),
    "后退":   Twist(linear=Vector3(x=-0.2, y=0.0, z=0.0)),
    "向后":   Twist(linear=Vector3(x=-0.2, y=0.0, z=0.0)),
    "向左":   Twist(linear=Vector3(x=0.0, y=0.2, z=0.0)),
    "向右":   Twist(linear=Vector3(x=0.0, y=-0.2, z=0.0)),
    "左转":   Twist(angular=Vector3(x=0.0, y=0.0, z=0.5)),
    "右转":   Twist(angular=Vector3(x=0.0, y=0.0, z=-0.5)),
    "停止":   Twist(),
    "停":     Twist(),
}

SERVO_CMD = {
    "看左边":  688,   # 舵机反装: 高脉冲=物理左
    "看右边":  312,   # 舵机反装: 低脉冲=物理右
    "回正":    500,
}

BUZZER_OK = BuzzerState(freq=600, on_time=0.05, off_time=0.01, repeat=1)
BUZZER_ERR = BuzzerState(freq=200, on_time=0.1, off_time=0.05, repeat=2)

# Movement duration per command (seconds)
MOTOR_DURATION = 0.5


class VoiceExecutorNode(Node):
    def __init__(self):
        super().__init__('voice_executor')

        # Publishers
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._servo_pub = self.create_publisher(ServosPosition, '/servo_controller', 10)
        self._buzzer_pub = self.create_publisher(BuzzerState,
            '/ros_robot_controller/set_buzzer', 10)
        self._led_pub = self.create_publisher(ColorRGBA, '/voice/status_led', 10)

        # Subscriber
        self.create_subscription(VoiceCommand, '/voice/voice_command',
            self.voice_callback, 10)

        # Timer for auto-stop after movement
        self._stop_timer = None
        self._has_pending_move = False

        self.get_logger().info('VoiceExecutor started')

    # ── Publish helpers ────────────────────────────────────────────

    def _pub_twist(self, twist: Twist, duration: float = 0.0):
        self._cmd_vel_pub.publish(twist)
        self.get_logger().info(
            f'Motor: linear({twist.linear.x:.1f},{twist.linear.y:.1f}) '
            f'angular({twist.angular.z:.1f})')
        # Schedule auto-stop
        if duration > 0 and (twist.linear.x != 0 or twist.linear.y != 0
                             or twist.angular.z != 0):
            if self._stop_timer:
                self._stop_timer.cancel()
            self._stop_timer = self.create_timer(duration, self._auto_stop)
            self._has_pending_move = True
        else:
            self._has_pending_move = False

    def _auto_stop(self):
        self._pub_twist(Twist(), 0.0)
        if self._stop_timer:
            self._stop_timer.cancel()
            self._stop_timer = None

    def _pub_servo(self, pulse: int):
        msg = ServosPosition()
        msg.duration = 0.3
        msg.position_unit = 'pulse'
        s = ServoPosition()
        s.id = 1
        s.position = float(pulse)
        msg.position = [s]
        self._servo_pub.publish(msg)
        self.get_logger().info(f'Servo: pulse={pulse}')

    def _pub_buzzer(self, state: BuzzerState):
        self._buzzer_pub.publish(state)

    def _pub_led(self, r: float, g: float, b: float, a: float = 1.0):
        msg = ColorRGBA(r=r, g=g, b=b, a=a)
        self._led_pub.publish(msg)

    # ── Voice callback ─────────────────────────────────────────────

    def voice_callback(self, msg: VoiceCommand):
        phrase = msg.command_text

        # Motor commands
        if phrase in MOTOR_CMD:
            twist = MOTOR_CMD[phrase]
            self._pub_twist(twist, MOTOR_DURATION)
            self._pub_buzzer(BUZZER_OK)
            self._pub_led(0.0, 0.5, 0.0)  # green
            return

        # Servo commands
        if phrase in SERVO_CMD:
            self._pub_servo(SERVO_CMD[phrase])
            self._pub_buzzer(BUZZER_OK)
            self._pub_led(0.0, 0.3, 0.8)  # blue
            return

        # Follow / navigation (placeholder — future)
        if phrase in ("过来", "跟着我"):
            self._pub_buzzer(BUZZER_OK)
            self._pub_led(1.0, 0.5, 0.0)  # orange
            self.get_logger().info(f'Follow mode requested — not yet implemented')
            return

        if phrase in ("回去",):
            self._pub_buzzer(BUZZER_OK)
            self._pub_led(1.0, 0.0, 0.5)  # purple
            self.get_logger().info(f'Return home requested — not yet implemented')
            return

        if phrase == "蜂鸣":
            self._pub_buzzer(BuzzerState(freq=2500, on_time=0.05,
                                          off_time=0.01, repeat=3))
            return

        # Unknown
        self._pub_buzzer(BUZZER_ERR)
        self._pub_led(1.0, 0.0, 0.0)  # red
        self.get_logger().warn(f'Unknown voice command: {phrase}')


def main(args=None):
    rclpy.init(args=args)
    node = VoiceExecutorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
