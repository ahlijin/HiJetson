cmake_minimum_required(VERSION 3.8)
project(vision_msgs)

find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Detection2D.msg"
  "msg/Detection2DArray.msg"
  "msg/VisionInfo.msg"
  DEPENDENCIES builtin_interfaces std_msgs
)

ament_package()