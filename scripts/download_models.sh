#!/bin/bash
#==============================================================================
# HiJetson 模型下载脚本
# 下载 YOLOv8 和 Whisper 模型文件
#==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/src/models"

echo "=== HiJetson 模型下载 ==="
echo ""

# YOLOv8
echo ">>> [1/2] 下载 YOLOv8 模型..."
mkdir -p $MODELS_DIR/yolo

if [ ! -f "$MODELS_DIR/yolo/yolov8n.onnx" ]; then
    echo "   下载 yolov8n.onnx..."
    wget -q --show-progress \
        https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.onnx \
        -O $MODELS_DIR/yolo/yolov8n.onnx
    echo "   YOLOv8n 下载完成"
else
    echo "   yolov8n.onnx 已存在"
fi

if [ ! -f "$MODELS_DIR/yolo/yolov8s.onnx" ]; then
    echo "   下载 yolov8s.onnx..."
    wget -q --show-progress \
        https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8s.onnx \
        -O $MODELS_DIR/yolo/yolov8s.onnx
    echo "   YOLOv8s 下载完成"
else
    echo "   yolov8s.onnx 已存在"
fi

# Whisper (faster-whisper 首次运行时自动下载)
echo ""
echo ">>> [2/2] Whisper 模型"
echo "   faster-whisper 首次运行 ASR 节点时自动下载"
echo "   模型缓存目录: ~/.cache/huggingface/hub/"
echo "   或运行: python3 -c \"from faster_whisper import WhisperModel; WhisperModel('base', device='cuda')\""

echo ""
echo "=== 完成 ==="