#!/bin/bash
#==============================================================================
# HiJetson 全系统启动脚本
# 启动所有模块: 语音采集 + VAD + ASR + 图像采集 + YOLO + 深度 + 融合
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================="
echo "  HiJetson 全系统启动"
echo "  设备: Jetson Orin Nano + Astra Pro"
echo "========================================="
echo ""

# 检查 ROS2 环境
if [ -z "$ROS_DISTRO" ]; then
    if [ -f "/opt/ros/humble/setup.bash" ]; then
        source /opt/ros/humble/setup.bash
    else
        echo "错误: 未检测到 ROS2 Humble"
        echo "请先: source /opt/ros/humble/setup.bash"
        exit 1
    fi
fi

# 加载工作空间
if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
else
    echo "警告: 未找到 install/setup.bash，请先编译:"
    echo "  cd $WORKSPACE_DIR && colcon build --symlink-install"
fi

# 启动 Astra Pro 相机
echo ">>> [1] 启动 Astra Pro 相机..."
ros2 launch astra_camera astra_pro.launch.py \
    color_width:=1280 color_height:=720 color_fps:=30 \
    enable_depth:=true \
    enable_ir:=false &
ASTRA_PID=$!
sleep 3

# 启动语音采集
echo ">>> [2] 启动语音采集..."
ros2 run voice_capture voice_capture_node \
    --ros-args -p sample_rate:=16000 -p frame_size:=1600 &
CAPTURE_PID=$!
sleep 1

# 启动 VAD
echo ">>> [3] 启动语音活动检测 (VAD)..."
ros2 run voice_vad voice_vad_node \
    --ros-args -p sample_rate:=16000 -p vad_mode:=1 &
VAD_PID=$!
sleep 1

# 启动 ASR
echo ">>> [4] 启动语音识别 (ASR)..."
ros2 run voice_asr voice_asr_node \
    --ros-args -p model_size:=base -p language:=zh &
ASR_PID=$!
sleep 1

# 启动图像预处理
echo ">>> [5] 启动图像预处理..."
ros2 run image_preprocess image_preprocess_node &
IMG_PID=$!
sleep 1

# 启动 YOLO 检测
echo ">>> [6] 启动目标检测 (YOLOv8)..."
ros2 run object_detection object_detection_node \
    --ros-args -p conf_threshold:=0.5 &
YOLO_PID=$!
sleep 1

# 启动深度处理器
echo ">>> [7] 启动深度处理器..."
ros2 run depth_processor depth_processor_node &
DEPTH_PID=$!
sleep 1

# 启动融合节点
echo ">>> [8] 启动融合节点..."
ros2 run fusion_node fusion_node &
FUSION_PID=$!
sleep 1

echo ""
echo "========================================="
echo "  所有模块已启动!"
echo "========================================="
echo ""
echo "按 Ctrl+C 停止所有进程"
echo ""
echo "查看话题列表: ros2 topic list"
echo "查看检测结果: ros2 topic echo /vision/detection_result"
echo "查看语音命令: ros2 topic echo /voice/voice_command"
echo "查看融合结果: ros2 topic echo /fusion/result"

# 等待并处理 Ctrl+C
cleanup() {
    echo ""
    echo "正在关闭所有进程..."
    kill $FUSION_PID $DEPTH_PID $YOLO_PID $IMG_PID $ASR_PID $VAD_PID $CAPTURE_PID $ASTRA_PID 2>/dev/null
    wait
    echo "已停止所有模块"
    exit 0
}
trap cleanup SIGINT SIGTERM

# 保持运行
wait