#!/bin/bash
# ReSpeaker Mic Array v2.0 一键设置
set -e

echo "=== 1. 加载 USB 音频内核模块 ==="
sudo modprobe snd-usb-audio 2>/dev/null && echo "OK" || echo "可能已加载"

echo ""
echo "=== 2. 安装 udev 规则 ==="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$SCRIPT_DIR/99-respeaker.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "OK"

echo ""
echo "=== 3. 安装 Python 依赖 ==="
pip3 install --user sounddevice numpy scipy openai-whisper openwakeword 2>&1 | tail -2

echo ""
echo "=== 4. 验证 ==="
lsusb | grep -i 2886 || echo "USB: 未检测到 (拔插一下)"
cat /proc/asound/cards | grep -i array || echo "ALSA: 未检测到 (可能需要拔插)"

echo ""
echo "完成！运行测试: python3 scripts/respeaker_asr_test.py"
