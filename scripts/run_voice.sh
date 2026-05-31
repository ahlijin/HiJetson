#!/bin/bash
#==============================================================================
# HiJetson 语音模块启动脚本
# 使用 ROS2 launch 文件启动语音采集 + VAD + ASR
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

echo ">>> 启动语音模块 (音频采集 + VAD + ASR) ..."
echo "    模型: faster-whisper base (CPU int8)"
echo "    麦克风: ASTRA Pro (PulseAudio)"
echo ""

ros2 launch "$WORKSPACE_DIR/src/launch/hijetson_voice.launch.py"
