#!/bin/bash
#==============================================================================
# HiJetson 清理脚本
# 清理编译产物和日志
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== HiJetson 清理 ==="
echo "工作空间: $WORKSPACE_DIR"
echo ""

clean_all=false
if [ "$1" == "--all" ]; then
    clean_all=true
fi

# 清理编译产物
echo ">>> 清理编译产物..."
rm -rf "$WORKSPACE_DIR/build" "$WORKSPACE_DIR/install" "$WORKSPACE_DIR/log"
echo "   已删除 build/ install/ log/"

if [ "$clean_all" = true ]; then
    echo ""
    echo ">>> 清理模型文件..."
    rm -rf "$WORKSPACE_DIR/src/models"/*
    echo "   已删除模型文件"

    echo ""
    echo ">>> 清理 ROS2 日志..."
    rm -rf ~/.ros/log
    echo "   已删除 ROS2 日志"
fi

echo ""
echo "=== 完成 ==="
echo ""
echo "重新编译: colcon build --symlink-install"