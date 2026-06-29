#!/bin/bash
#==============================================================================
# HiJetson 视觉模块启动脚本
# 仅启动: 图像采集 + 预处理 + YOLO + 深度处理
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$ROS_DISTRO" ]; then
    source /opt/ros/humble/setup.bash 2>/dev/null || true
fi

if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
fi

echo ">>> 启动 Astra Pro 相机..."
ros2 launch astra_camera astra_pro.launch.py \
    color_width:=1280 color_height:=720 color_fps:=30 \
    enable_depth:=true &
PID1=$!
sleep 3

echo ">>> 启动图像预处理..."
ros2 run image_preprocess image_preprocess_node &
PID2=$!
sleep 1

echo ">>> 启动 YOLOv8 检测..."
ros2 run object_detection object_detection_node --ros-args -p conf_threshold:=0.5 &
PID3=$!
sleep 1

echo ">>> 启动深度处理器..."
ros2 run depth_processor depth_processor_node &
PID4=$!

echo "视觉模块已启动"
echo "按 Ctrl+C 停止"

cleanup() { kill $PID1 $PID2 $PID3 $PID4 2>/dev/null; exit 0; }
trap cleanup SIGINT SIGTERM
wait