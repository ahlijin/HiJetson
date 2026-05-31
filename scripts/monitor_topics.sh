#!/bin/bash
#==============================================================================
# HiJetson 话题监控脚本
# 实时显示关键话题数据
#==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -z "$ROS_DISTRO" ]; then
    source /opt/ros/humble/setup.bash 2>/dev/null || true
fi

if [ -f "$WORKSPACE_DIR/install/setup.bash" ]; then
    source "$WORKSPACE_DIR/install/setup.bash"
fi

clear
echo "================================================"
echo "  HiJetson 实时监控"
echo "================================================"
echo ""
echo "话题列表:"
ros2 topic list
echo ""
echo "--- 语音活动 ---"
echo "ros2 topic echo /voice/voice_activity --once"
echo ""
echo "--- 语音命令 ---"
echo "ros2 topic echo /voice/voice_command --once"
echo ""
echo "--- 检测结果 ---"
echo "ros2 topic echo /vision/detection_result --once"
echo ""
echo "--- 融合结果 ---"
echo "ros2 topic echo /fusion/result --once"
echo ""
echo "--- 节点列表 ---"
ros2 node list
echo ""
echo "按任意键刷新, Ctrl+C 退出"