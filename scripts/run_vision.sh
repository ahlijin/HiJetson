#!/bin/bash
#==============================================================================
# HiJetson 视觉模块启动脚本
# Astra Pro 相机 + 深度处理（= hijetson_vision.launch.py）
#
# 注：原脚本手工 ros2 run 了 image_preprocess / object_detection 两个本仓库不存在的包，
#     已统一改为走 hijetson_bringup 的 launch（那两个模块等实现后再加回 launch 里）。
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$ROS_DISTRO" ]; then
    source /opt/ros/humble/setup.bash 2>/dev/null || true
fi

if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
elif [ -f /opt/hijetson/install/setup.bash ]; then
    source /opt/hijetson/install/setup.bash
else
    echo "错误：找不到 install/setup.bash（先在 $WORKSPACE_DIR 里 colcon build）" >&2
    exit 1
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"

echo ">>> 启动视觉模块 (Astra Pro 相机 + 深度处理)"
echo "    ROS_DOMAIN_ID=$ROS_DOMAIN_ID，按 Ctrl+C 停止"
echo ""

exec ros2 launch hijetson_bringup hijetson_vision.launch.py "$@"
