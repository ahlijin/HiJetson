#!/bin/bash
#==============================================================================
# HiJetson 语音模块启动脚本
# 采集 → VAD → 唤醒词 → 反馈音 → ASR → DOA → 声源跟踪 → 指令执行
# 参数在 hijetson_bringup 包的 config/voice_params.yaml
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$ROS_DISTRO" ]; then
    source /opt/ros/humble/setup.bash 2>/dev/null || true
fi

# 工作空间：优先用仓库里的 install，其次是部署形态 /opt/hijetson
if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
elif [ -f /opt/hijetson/install/setup.bash ]; then
    source /opt/hijetson/install/setup.bash
else
    echo "错误：找不到 install/setup.bash（先在 $WORKSPACE_DIR 里 colcon build）" >&2
    exit 1
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"

echo ">>> 启动语音模块 (采集 -> VAD -> 唤醒词 -> 反馈音 -> ASR -> DOA -> servo_tracker -> executor)"
echo "    ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
echo ""

exec ros2 launch hijetson_bringup hijetson_voice.launch.py "$@"
