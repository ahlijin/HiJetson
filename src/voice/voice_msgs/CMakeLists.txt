cmake_minimum_required(VERSION 3.8)
project(voice_msgs)

find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/VoiceCommand.msg"
  DEPENDENCIES builtin_interfaces std_msgs
)

ament_package()