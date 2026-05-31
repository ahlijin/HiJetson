#!/bin/bash
#==============================================================================
# HiJetson 语音模块启动脚本
# 仅启动: 语音采集 + VAD + ASR
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

echo ">>> 启动语音采集..."
ros2 run voice_capture voice_capture_node --ros-args -p sample_rate:=16000 &
PID1=$!
sleep 1

echo ">>> 启动 VAD..."
ros2 run voice_vad voice_vad_node --ros-args -p sample_rate:=16000 -p vad_mode:=1 &
PID2=$!
sleep 1

echo ">>> 启动 ASR..."
ros2 run voice_asr voice_asr_node --ros-args -p model_size:=base -p language:=zh &
PID3=$!

echo "语音模块已启动 (PID: $PID1 $PID2 $PID3)"
echo "按 Ctrl+C 停止"

cleanup() { kill $PID1 $PID2 $PID3 2>/dev/null; exit 0; }
trap cleanup SIGINT SIGTERM
wait