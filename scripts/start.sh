#!/bin/bash
#==============================================================================
# HiJetson 容器主进程（部署到 /opt/hijetson/start.sh，由 docker compose 调起）
#
# 【启动什么由这个脚本决定，compose 只负责跑它】要换管线只改下面 LAUNCH 那一行：
#   LAUNCH=hijetson_voice.launch.py    语音链路（采集/VAD/热词/反馈/ASR/DOA/跟踪/执行）
#   LAUNCH=hijetson_vision.launch.py   相机 + 深度处理
#   LAUNCH=hijetson_all.launch.py      全量（相机+语音+深度+融合+跟踪）
#   LAUNCH=shell                       进交互 bash 调试
#
# 其它环境变量（一般不用动）：
#   HIJETSON_LAUNCH 临时覆盖 LAUNCH（调试用：docker compose run --rm -e HIJETSON_LAUNCH=shell hijetson-ros）
#   HIJETSON_WS     工作空间目录（默认 /opt/hijetson）
#   ROS_DOMAIN_ID   默认 42（要和 Pi3 侧一致才能互通）
#
# 说明：
#   - 不再用 `sleep infinity` 占位：容器退出=管线退出，配合 compose 的
#     restart: unless-stopped 能自动重启
#   - 用 exec 启动 ros2 launch，让它成为容器主进程，docker stop 时能收到信号收尾
#==============================================================================

set -e

WS="${HIJETSON_WS:-/opt/hijetson}"

# ↓↓↓ 启动哪个管线：改这一行 ↓↓↓
LAUNCH="${HIJETSON_LAUNCH:-hijetson_voice.launch.py}"

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"

if [ -f /opt/ros/humble/setup.bash ]; then
    # shellcheck disable=SC1091
    source /opt/ros/humble/setup.bash
else
    echo "[start.sh] 错误：没找到 /opt/ros/humble/setup.bash" >&2
    exit 1
fi

if [ -f "$WS/install/setup.bash" ]; then
    # shellcheck disable=SC1091
    source "$WS/install/setup.bash"
else
    echo "[start.sh] 错误：$WS/install/setup.bash 不存在（部署包没解开？）" >&2
    exit 1
fi

echo "[start.sh] ws=$WS launch=$LAUNCH ROS_DOMAIN_ID=$ROS_DOMAIN_ID"

if [ "$LAUNCH" = "shell" ]; then
    echo "[start.sh] 进入交互 shell（HIJETSON_LAUNCH=shell）"
    exec bash
fi

# 设备若还没枚举出来（容器先于 USB 起来），等一会儿再启动，避免白重启
if [ ! -e /dev/snd ] && [ ! -e /dev/video0 ]; then
    echo "[start.sh] 还没看到 /dev/snd 与 /dev/video0，等 10s 再启动..." >&2
    sleep 10
fi

exec ros2 launch hijetson_bringup "$LAUNCH"
