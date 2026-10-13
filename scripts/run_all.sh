#!/bin/bash
#==============================================================================
# HiJetson 全系统启动脚本
# 相机 + 语音链路 + 深度处理 + 融合 + 声源跟踪（= hijetson_all.launch.py）
#
# 注：原来的手工 ros2 run 列表里引用了 image_preprocess / object_detection 两个
#     不存在的包，且与 launch 文件重复维护 —— 现在统一走 hijetson_bringup 的 launch。
#     需要单独调试某个模块时用 scripts/run_voice.sh / run_vision.sh，或 HIJETSON_LAUNCH=shell。
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================="
echo "  HiJetson 全系统启动 (相机+语音+深度+融合)"
echo "  设备: Jetson Orin Nano + Astra Pro + ReSpeaker"
echo "========================================="
echo ""

if [ -z "$ROS_DISTRO" ]; then
    source /opt/ros/humble/setup.bash 2>/dev/null || true
fi

if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
elif [ -f /opt/hijetson/install/setup.bash ]; then
    source /opt/hijetson/install/setup.bash
else
    echo "错误：找不到 install/setup.bash，请先在 $WORKSPACE_DIR 编译：" >&2
    echo "  cd $WORKSPACE_DIR && colcon build" >&2
    exit 1
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
echo ">>> ROS_DOMAIN_ID=$ROS_DOMAIN_ID，按 Ctrl+C 停止"
echo ""

exec ros2 launch hijetson_bringup hijetson_all.launch.py "$@"
