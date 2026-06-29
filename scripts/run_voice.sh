#!/bin/bash
#==============================================================================
# HiJetson 语音模块启动脚本
# 使用 ROS2 launch 文件启动语音采集 + VAD + 唤醒词 + 反馈提示音 + ASR
#
# capture 和 feedback 都走 PulseAudio 默认设备，无需手动释放麦克风。
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

echo ">>> 启动语音模块 (采集 -> VAD -> 唤醒词 -> 反馈音 -> ASR) ..."
echo "    模型: whisper small (CUDA)"
echo "    全部走 PulseAudio 默认设备 (输入+输出都走PA)"
echo ""

exec env PULSE_SERVER=/run/user/1000/pulse/native \
    ros2 launch "$WORKSPACE_DIR/src/launch/hijetson_voice.launch.py"
