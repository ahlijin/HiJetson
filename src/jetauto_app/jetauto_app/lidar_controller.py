#!/usr/bin/env python3
# encoding: utf-8
"""
雷达避障，跟随功能 (Lidar obstacle avoidance and lidar following)

Port from the original HiWonder JetAuto app, adapted for HiJetson.
- mode 1: obstacle avoidance
- mode 2: laser following
- mode 3: laser guarding
"""
import os
import math
import time
import rclpy
import threading
import numpy as np
from rclpy.node import Node
from std_srvs.srv import Trigger
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from interfaces.srv import SetInt64, SetFloat64List
from ros_robot_controller_msgs.msg import ServosPosition, ServoPosition
from rclpy.qos import QoSProfile, QoSReliabilityPolicy
from jetauto_app.pid import PID
from jetauto_app.common import set_range

CAR_WIDTH = 0.4          # meter
MAX_SCAN_ANGLE = 240     # laser scanning angle, exclude the always-occluded part


class LidarController(Node):
    def __init__(self, name):
        super().__init__(name)

        self.name = name
        self.running_mode = 0
        self.threshold = 0.6         # meters
        self.scan_angle = math.radians(90)  # radians
        self.speed = 0.2
        self.last_act = 0
        self.timestamp = 0
        self.angle_data = []
        # PID params
        self.pid_yaw = PID(1.6, 0, 0.16)
        self.pid_dist = PID(1.7, 0, 0.16)
        self.lock = threading.RLock()
        self.lidar_sub = None
        self.lidar_type = os.environ.get('LIDAR_TYPE', 'A1')
        self.mecanum_pub = self.create_publisher(Twist, '/controller/cmd_vel', 1)
        self.joints_pub = self.create_publisher(ServosPosition, '/servo_controller', 1)

        # Services
        self.create_service(Trigger, '~/enter', self.enter_srv_callback)
        self.create_service(Trigger, '~/exit', self.exit_srv_callback)
        self.create_service(SetInt64, '~/set_running', self.set_running_srv_callback)
        self.create_service(SetFloat64List, '~/set_param', self.set_parameters_srv_callback)
        self.create_service(Trigger, '~/init_finish', self.get_node_state)

        self.get_logger().info('\033[1;32m%s\033[0m' % 'lidar_controller start')

    def get_node_state(self, request, response):
        response.success = True
        return response

    def reset_value(self):
        self.running_mode = 0
        self.threshold = 0.6
        self.scan_angle = math.radians(90)
        self.speed = 0.2
        self.last_act = 0
        self.timestamp = 0
        self.pid_yaw.clear()
        self.pid_dist.clear()

    def _set_servo_default_pose(self):
        """Set camera gimbal to default forward-looking pose."""
        msg = ServosPosition()
        msg.duration = 1.0
        msg.position_unit = "pulse"
        poses = [(10, 300), (5, 500), (4, 210), (3, 40), (2, 665), (1, 500)]
        msg.position = [ServoPosition(id=i, position=float(p)) for i, p in poses]
        self.joints_pub.publish(msg)

    def enter_srv_callback(self, request, response):
        self.get_logger().info('\033[1;32m%s\033[0m' % 'lidar enter')
        self.reset_value()
        qos = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT)
        self.lidar_sub = self.create_subscription(LaserScan, '/scan_raw', self.lidar_callback, qos)
        self._set_servo_default_pose()
        response.success = True
        response.message = "enter"
        return response

    def exit_srv_callback(self, request, response):
        self.get_logger().info('\033[1;32m%s\033[0m' % 'lidar exit')
        self.reset_value()
        self.mecanum_pub.publish(Twist())
        response.success = True
        response.message = "exit"
        return response

    def set_running_srv_callback(self, request, response):
        """
        Set running mode:
          0 = stop
          1 = obstacle avoidance
          2 = laser following
          3 = laser guarding
        """
        self.get_logger().info(str(request))
        new_mode = request.data
        self.get_logger().info('\033[1;32m%s\033[0m' % ("set_running " + str(new_mode)))
        if not 0 <= new_mode <= 3:
            response.success = False
            response.message = "Invalid running mode {}".format(new_mode)
        else:
            response.success = True
            response.message = "set_running"
            with self.lock:
                self.running_mode = new_mode
        self.mecanum_pub.publish(Twist())
        return response

    def set_parameters_srv_callback(self, request, response):
        """Set obstacle avoidance threshold, scan angle, and speed."""
        new_threshold, new_scan_angle, new_speed = request.data
        self.get_logger().info(
            "\033[1;32mn_t:{:.2f}, n_a:{:.2f}, n_s:{:.2f}\033[0m".format(
                new_threshold, new_scan_angle, new_speed
            )
        )
        if not 0.3 <= new_threshold <= 1.5:
            response.success = False
            response.message = "New threshold ({:.2f}) out of range (0.3~1.5)".format(new_threshold)
            return response
        if not 0 <= new_scan_angle <= 90:
            response.success = False
            response.message = "New scan angle ({:.2f}) out of range (0~90)".format(new_scan_angle)
            return response
        if not new_speed > 0:
            response.success = False
            response.message = "Invalid speed"
            return response

        with self.lock:
            self.threshold = new_threshold
            self.scan_angle = math.radians(new_scan_angle)
            self.speed = new_speed
        return response

    def lidar_callback(self, lidar_data):
        twist = Twist()
        # data size = scan angle / angle increment
        if self.lidar_type != 'G4':
            max_index = int(math.radians(MAX_SCAN_ANGLE / 2.0) / lidar_data.angle_increment)
            left_ranges = lidar_data.ranges[:max_index]
            right_ranges = lidar_data.ranges[::-1][:max_index]
        else:
            min_index = int(math.radians((360 - MAX_SCAN_ANGLE) / 2.0) / lidar_data.angle_increment)
            max_index = min_index + int(math.radians(MAX_SCAN_ANGLE / 2.0) / lidar_data.angle_increment)
            left_ranges = lidar_data.ranges[::-1][min_index:max_index][::-1]
            right_ranges = lidar_data.ranges[min_index:max_index][::-1]

        with self.lock:
            angle = self.scan_angle / 2
            angle_index = int(angle / lidar_data.angle_increment + 0.50)
            lr = np.array(left_ranges[:angle_index])
            rr = np.array(right_ranges[:angle_index])

            if self.running_mode == 1 and self.timestamp <= time.time():
                # ----- Obstacle avoidance -----
                left_nonzero = lr.nonzero()
                right_nonzero = rr.nonzero()
                left_nonan = np.isfinite(lr[left_nonzero])
                right_nonan = np.isfinite(rr[right_nonzero])
                min_left_ = lr[left_nonzero][left_nonan]
                min_right_ = rr[right_nonzero][right_nonan]

                if len(min_left_) > 1 and len(min_right_) > 1:
                    min_left = min_left_.min()
                    min_right = min_right_.min()

                    if min_left <= self.threshold and min_right > self.threshold:
                        # obstacle on left
                        twist.linear.x = self.speed / 6
                        w = self.speed * 6.0
                        twist.angular.z = -w
                        if self.last_act != 0 and self.last_act != 1:
                            twist.angular.z = w
                        self.last_act = 1
                        self.mecanum_pub.publish(twist)
                        self.timestamp = time.time() + (math.radians(90) / w / 2)

                    elif min_left <= self.threshold and min_right <= self.threshold:
                        # obstacle on both sides
                        twist.linear.x = self.speed / 6
                        w = self.speed * 6.0
                        twist.angular.z = w
                        self.last_act = 3
                        self.mecanum_pub.publish(twist)
                        self.timestamp = time.time() + (math.radians(180) / w / 2)

                    elif min_left > self.threshold and min_right <= self.threshold:
                        # obstacle on right
                        twist.linear.x = self.speed / 6
                        w = self.speed * 6.0
                        twist.angular.z = w
                        if self.last_act != 0 and self.last_act != 2:
                            twist.angular.z = -w
                        self.last_act = 2
                        self.mecanum_pub.publish(twist)
                        self.timestamp = time.time() + (math.radians(90) / w / 2)

                    else:
                        # no obstacle
                        self.last_act = 0
                        twist.linear.x = self.speed
                        self.mecanum_pub.publish(twist)

            elif self.running_mode == 2:
                # ----- Laser following -----
                ranges = np.append(rr[::-1], lr)
                nonzero = ranges.nonzero()
                nonan = np.isfinite(ranges[nonzero])
                dist_ = ranges[nonzero][nonan]
                if len(dist_) > 0:
                    dist = dist_.min()
                    min_index = list(ranges).index(dist)
                    angle_offset = -angle + lidar_data.angle_increment * min_index

                    # yaw control
                    if dist < self.threshold and abs(math.degrees(angle_offset)) > 5:
                        if self.lidar_type != 'G4':
                            self.pid_yaw.update(-angle_offset)
                            twist.angular.z = set_range(self.pid_yaw.output, -self.speed * 6.0, self.speed * 6.0)
                        else:
                            self.pid_yaw.update(angle_offset)
                            twist.angular.z = -set_range(self.pid_yaw.output, -self.speed * 6.0, self.speed * 6.0)
                    else:
                        self.pid_yaw.clear()

                    # distance control
                    if dist < self.threshold and abs(0.2 - dist) > 0.02:
                        self.pid_dist.update(self.threshold / 2 - dist)
                        twist.linear.x = set_range(self.pid_dist.output, -self.speed, self.speed)
                    else:
                        self.pid_dist.clear()

                    if abs(twist.angular.z) < 0.008:
                        twist.angular.z = 0.0
                    if abs(twist.linear.x) < 0.05:
                        twist.linear.x = 0.0
                    self.mecanum_pub.publish(twist)

            elif self.running_mode == 3:
                # ----- Laser guarding -----
                ranges = np.append(rr[::-1], lr)
                nonzero = ranges.nonzero()
                nonan = np.isfinite(ranges[nonzero])
                dist_ = ranges[nonzero][nonan]
                if len(dist_) > 1:
                    dist = dist_.min()
                    min_index = list(ranges).index(dist)
                    angle_offset = -angle + lidar_data.angle_increment * min_index

                    if dist < self.threshold and abs(math.degrees(angle_offset)) > 5:
                        if self.lidar_type != 'G4':
                            self.pid_yaw.update(-angle_offset)
                            twist.angular.z = set_range(self.pid_yaw.output, -self.speed * 6.0, self.speed * 6.0)
                        else:
                            self.pid_yaw.update(angle_offset)
                            twist.angular.z = -set_range(self.pid_yaw.output, -self.speed * 6.0, self.speed * 6.0)
                    else:
                        self.pid_yaw.clear()

                    if abs(twist.angular.z) < 0.008:
                        twist.angular.z = 0.0
                    self.mecanum_pub.publish(twist)


def main():
    rclpy.init()
    node = LidarController('lidar_app')
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
