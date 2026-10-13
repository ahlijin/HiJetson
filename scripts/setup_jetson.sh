#!/bin/bash
#==============================================================================
# HiJetson 环境安装脚本 (Jetson Orin Nano) —— 【宿主机原生安装，老流程】
#
# 注意(2026-10 起)：Jetson 已升级到 JetPack 7 / Ubuntu 24.04，宿主机装不上 ROS2 Humble，
# 现在推荐的做法是"全部跑在容器里"：
#     docker/ 目录下的 Dockerfile.my-ros（镜像，推送到 gitea registry）
#   + docker/docker-compose.yml（/dev:/dev、privileged、host 网络、ROS_DOMAIN_ID=42）
# 本脚本仅用于"宿主机原生跑 22.04 老流程"的场合，或作为依赖清单参考。
#
# 国内网络：默认把 apt / pip 换成国内镜像（清华源），不想要就 `SKIP_MIRROR=1 bash setup_jetson.sh`
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

# 0. 国内镜像源（apt + pip）
if [ "${SKIP_MIRROR:-0}" != "1" ]; then
    echo ""
    echo ">>> [0/8] 切换国内镜像源 (清华 tuna)..."
    # apt: ubuntu-ports（arm64 的源）+ ROS2 源
    if [ -f /etc/apt/sources.list ]; then
        sudo sed -i 's|http://ports.ubuntu.com/ubuntu-ports|https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports|g' /etc/apt/sources.list
    fi
    for f in /etc/apt/sources.list.d/*.sources; do
        [ -f "$f" ] || continue
        sudo sed -i 's|http://ports.ubuntu.com/ubuntu-ports|https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports|g' "$f"
    done
    for f in /etc/apt/sources.list.d/*ros*.list /etc/apt/sources.list.d/ros2*.list; do
        [ -f "$f" ] || continue
        sudo sed -i 's|http://packages.ros.org/ros2/ubuntu|https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu|g' "$f"
    done
    # pip: 全局配置（系统级 /etc/pip.conf）
    sudo mkdir -p /etc
    printf '[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ntrusted-host = pypi.tuna.tsinghua.edu.cn\n' | sudo tee /etc/pip.conf >/dev/null
    echo "    apt/pip 镜像已设置 (可用 SKIP_MIRROR=1 跳过)"
fi

# 1. 系统依赖
echo ""
echo ">>> [1/8] 安装系统依赖..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-numpy python3-opencv \
    libopenblas-dev libomp-dev \
    portaudio19-dev python3-pyaudio \
    libportaudio2 alsa-utils libusb-1.0-0 \
    cmake build-essential

# 2. ROS2 Humble 安装 (如果尚未安装)
echo ""
echo ">>> [2/8] 检查 ROS2 Humble..."
if [ ! -f "/opt/ros/humble/setup.bash" ]; then
    echo "安装 ROS2 Humble..."
    sudo apt-get install -y ros-humble-desktop python3-rosdep
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
else
    echo "ROS2 Humble 已安装"
fi

# 3. ROS2 依赖
echo ""
echo ">>> [3/8] 安装 ROS2 依赖..."
sudo apt-get install -y \
    ros-humble-cv-bridge ros-humble-image-transport \
    ros-humble-camera-info-manager \
    ros-humble-launch-ros

# 4. Python 依赖
echo ""
echo ">>> [4/8] 安装 Python 依赖..."
python3 -m pip install --upgrade pip

# TensorRT + ONNX (Jetson 预装)
echo "   - onnxruntime-gpu (Jetson 版)"
python3 -m pip install onnxruntime-gpu==1.17.1

# 语音/音频/USB（麦克风阵列 + DOA + LED 环）
echo "   - 语音依赖 (sounddevice / pyusb / hidapi / pixel-ring)"
python3 -m pip install sounddevice pyusb pixel-ring hidapi

# Whisper (openai-whisper, PyTorch CUDA)
echo "   - openai-whisper (PyTorch CUDA)"
python3 -m pip install openai-whisper

# 修复 numba + coverage 兼容性问题
echo "   - 修复 numba/coverage 兼容性"
python3 -m pip install "coverage==6.5.0"

# 5. Orbbec Astra Pro 驱动 (git submodule, 来源为本地 gitea)
echo ""
echo ">>> [5/8] 初始化 Orbbec Astra Pro 驱动子模块..."
git submodule update --init --recursive src/orbbec_ws

# 6. 下载 YOLOv8 模型
echo ""
echo ">>> [6/8] 下载 YOLOv8 模型..."
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
echo ">>> [7/8] 编译 ROS2 工作空间..."
source /opt/ros/humble/setup.bash

# 先编译 Orbbec 驱动
cd src/orbbec_ws
colcon build --symlink-install
cd ../..

# 编译全部
colcon build --symlink-install

# 8. udev 规则（ReSpeaker / Orbbec 的 USB 权限，非 root 访问 /dev/bus/usb 需要）
echo ""
echo ">>> [8/8] 安装 udev 规则..."
if [ -f scripts/99-respeaker.rules ]; then
    sudo cp scripts/99-respeaker.rules /etc/udev/rules.d/
fi
sudo udevadm control --reload-rules && sudo udevadm trigger || true

echo ""
echo "=== 安装完成! ==="
echo ""
echo "首次启动前需停止 PulseAudio:"
echo "  systemctl --user stop pulseaudio.service pulseaudio.socket"
echo ""
echo "启动语音模块:"
echo "  source install/setup.bash"
echo "  ros2 launch hijetson_bringup hijetson_voice.launch.py"
echo ""
echo "查看识别结果:"
echo "  source install/setup.bash"
echo "  ros2 topic echo /voice/asr_result"
