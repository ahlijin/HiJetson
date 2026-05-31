#!/bin/bash
#==============================================================================
# HiJetson 环境安装脚本 (Jetson Orin Nano)
# 在 Jetson Orin Nano 上首次配置时运行
#==============================================================================

set -e

echo "=== HiJetson 环境安装脚本 ==="
echo "目标设备: Jetson Orin Nano 8G + Orbbec Astra Pro"
echo ""

# 检查架构
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ]; then
    echo "警告: 当前架构是 $ARCH，不是 aarch64 (Jetson)"
    echo "此脚本设计用于 Jetson Orin Nano"
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 1. 系统依赖
echo ""
echo ">>> [1/7] 安装系统依赖..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-numpy python3-opencv \
    libopenblas-dev libomp-dev \
    portaudio19-dev python3-pyaudio \
    cmake build-essential

# 2. ROS2 Humble 安装 (如果尚未安装)
echo ""
echo ">>> [2/7] 检查 ROS2 Humble..."
if [ ! -f "/opt/ros/humble/setup.bash" ]; then
    echo "安装 ROS2 Humble..."
    sudo apt-get install -y ros-humble-desktop python3-rosdep
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
else
    echo "ROS2 Humble 已安装"
fi

# 3. ROS2 依赖
echo ""
echo ">>> [3/7] 安装 ROS2 依赖..."
sudo apt-get install -y \
    ros-humble-cv-bridge ros-humble-image-transport \
    ros-humble-camera-info-manager \
    ros-humble-launch-ros

# 4. Python 依赖
echo ""
echo ">>> [4/7] 安装 Python 依赖..."
pip3 install --upgrade pip

# TensorRT + ONNX (Jetson 预装)
echo "   - onnxruntime-gpu (Jetson 版)"
pip3 install onnxruntime-gpu==1.17.1

# 语音
echo "   - 语音依赖"
pip3 install sounddevice webrtcvad

# Whisper (openai-whisper, PyTorch CUDA)
echo "   - openai-whisper (PyTorch CUDA)"
pip3 install openai-whisper

# 修复 numba + coverage 兼容性问题
echo "   - 修复 numba/coverage 兼容性"
pip3 install "coverage==6.5.0"

# 5. Orbbec Astra Pro 驱动
echo ""
echo ">>> [5/7] 安装 Orbbec Astra Pro 驱动..."
if [ ! -d "src/orbbec_ws" ]; then
    mkdir -p src/orbbec_ws
fi

cd src/orbbec_ws
if [ ! -d "astra_camera" ]; then
    git clone https://github.com/orbbec/ros2_astra_camera.git -b ros2 astra_camera
fi
cd ../..

# 6. 下载 YOLOv8 模型
echo ""
echo ">>> [6/7] 下载 YOLOv8 模型..."
mkdir -p src/models/yolo
if [ ! -f "src/models/yolo/yolov8n.onnx" ]; then
    wget -q https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.onnx \
        -O src/models/yolo/yolov8n.onnx
    echo "   YOLOv8n 模型已下载"
else
    echo "   YOLOv8n 模型已存在"
fi

# 7. 编译工作空间
echo ""
echo ">>> [7/7] 编译 ROS2 工作空间..."
source /opt/ros/humble/setup.bash

# 先编译 Orbbec 驱动
cd src/orbbec_ws
colcon build --symlink-install
cd ../..

# 编译全部
colcon build --symlink-install

echo ""
echo "=== 安装完成! ==="
echo ""
echo "首次启动前需停止 PulseAudio:"
echo "  systemctl --user stop pulseaudio.service pulseaudio.socket"
echo ""
echo "启动语音模块:"
echo "  source install/setup.bash"
echo "  ros2 launch src/launch/hijetson_voice.launch.py"
echo ""
echo "查看识别结果:"
echo "  source install/setup.bash"
echo "  ros2 topic echo /voice/asr_result"
