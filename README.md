# HiJetson — Jetson Orin Nano × Orbbec Astra Pro 多模态感知系统

## 项目概述

HiJetson 是一个基于 **NVIDIA Jetson Orin Nano 8G** 平台，配合 **Orbbec Astra Pro** 深度相机的多模态感知系统。项目集成**语音采集/识别**与**图像采集/识别**两个核心功能模块，为机器人、智能监控、边缘 AI 等场景提供完整的感知解决方案。

## 硬件平台

| 组件 | 型号 | 说明 |
|------|------|------|
| 核心计算平台 | NVIDIA Jetson Orin Nano 8GB | Ampere GPU (1024 CUDA cores, 32 Tensor Cores), 6核 ARM Cortex-A78AE CPU, 40 TOPS AI算力 |
| 深度相机 | Orbbec Astra Pro | RGB 1080P + Depth 640×480 + IR，内置单声道麦克风，支持结构光深度感知 |
| 麦克风 | Orbbec Astra Pro 内置麦克风 | USB Audio 设备，ALSA card 0 (Pro [ASTRA Pro])，可直接通过 ALSA 驱动采集 |
| 存储 | NVMe SSD 233GB | `/dev/nvme0n1p1`，已用 94G，可用 129G |

## 环境软件栈

| 项目 | 版本 |
|------|------|
| JetPack | **R36.5.0** (L4T 36.5.0) |
| 系统 | Ubuntu **22.04.5 LTS** (Jammy) |
| CUDA | **12.6.11** |
| TensorRT | **10.7.0.23** |
| ROS2 | **Humble** |
| Python | 3.10.12 |
| PyTorch | **2.5.0a0+nv24.08** (NVIDIA JetPack 优化版) |
| OpenCV | **4.10.0** |
| ONNX Runtime | **1.20.0** |
| sounddevice | **0.5.5** |

## 软件架构

```
┌──────────────────────────────────────────────────────────────┐
│                     HiJetson 多模态感知系统                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────────────┐  │
│  │   语音处理流水线      │    │      视觉处理流水线          │  │
│  │                     │    │                             │  │
│  │  ┌───────────────┐  │    │  ┌───────────────────────┐ │  │
│  │  │ 音频采集节点    │  │    │  │ 相机驱动节点          │ │  │
│  │  │ (ASTRA Pro麦克风)│  │    │  │ (ros2_astra_camera)  │ │  │
│  │  └───────┬───────┘  │    │  └────────┬──────────────┘ │  │
│  │          │          │    │           │                │  │
│  │  ┌───────▼───────┐  │    │  ┌────────▼──────────────┐ │  │
│  │  │ 语音活动检测    │  │    │  │ 图像预处理节点        │ │  │
│  │  │ (VAD)         │  │    │  │ (色彩校正/缩放/裁切)    │ │  │
│  │  └───────┬───────┘  │    │  └────────┬──────────────┘ │  │
│  │          │          │    │           │                │  │
│  │  ┌───────▼───────┐  │    │  ┌────────▼──────────────┐ │  │
│  │  │ 语音识别节点    │  │    │  │ 目标检测/识别节点     │ │  │
│  │  │ (Whisper + TRT) │  │    │  │ (YOLO + TensorRT)   │ │  │
│  │  └───────┬───────┘  │    │  └────────┬──────────────┘ │  │
│  │          │          │    │           │                │  │
│  │          │          │    │  ┌────────▼──────────────┐ │  │
│  │          │          │    │  │ 深度处理节点           │ │  │
│  │          │          │    │  │ (点云/距离测量)        │ │  │
│  │  ┌───────▼────────┐ │    │  └────────┬──────────────┘ │  │
│  │  │  决策/融合节点   │ │    └───────────┼──────────────┘  │
│  │  │  (多模态融合)    │◄─┼────────────────┘                │
│  │  └───────┬────────┘ │                                     │
│  │          │          │                                     │
│  │  ┌───────▼────────┐ │                                     │
│  │  │  应用层         │ │                                     │
│  │  │ (控制/显示/交互) │ │                                     │
│  │  └────────────────┘ │                                     │
│  └──────────────────────┘                                     │
│                                                               │
│  ════════════════════════════════════════════════════════     │
│  底层: ROS2 Humble + CUDA 12.6 + TensorRT 10.7 + Python 3.10 │
└───────────────────────────────────────────────────────────────┘
```

## 项目目录结构

```
HiJetson/
├── README.md                      # 项目概述
├── docs/                          # 详细文档
│   ├── design.md                  # 详细设计（模块/消息/话题/性能）
│   └── deployment.md              # 部署指南（安装/启动/清理）
├── src/
│   ├── orbbec_ws/                 # Orbbec Astra Pro ROS2驱动 (submodule)
│   │   └── astra_camera/
│   ├── voice_capture/             # 音频采集节点 (sounddevice, 16kHz PCM)
│   ├── voice_vad/                 # 语音活动检测节点 (WebRTC VAD)
│   ├── voice_asr/                 # 语音识别节点 (faster-whisper, GPU加速)
│   ├── voice_msgs/                # 语音模块自定义消息
│   ├── image_preprocess/          # 图像预处理节点 (resize/normalize)
│   ├── object_detection/          # 目标检测节点 (YOLOv8 + ONNX Runtime)
│   ├── depth_processor/           # 深度处理节点 (深度图 ROI 距离估算)
│   ├── vision_msgs/               # 视觉模块自定义消息
│   ├── fusion_node/               # 多模态融合节点
│   ├── fusion_msgs/               # 融合模块自定义消息
│   ├── models/                    # 模型文件目录
│   │   └── yolo/                  # YOLO ONNX 模型
│   ├── config/                    # 配置文件
│   │   ├── voice_params.yaml      # 语音模块参数
│   │   ├── vision_params.yaml     # 视觉模块参数
│   │   └── system_params.yaml     # 系统通用参数
│   └── launch/                    # ROS2 启动文件
│       ├── hijetson_all.launch.py # 全系统启动
│       ├── hijetson_voice.launch.py # 仅语音模块
│       └── hijetson_vision.launch.py # 仅视觉模块
├── scripts/                       # 部署 & 启动脚本
│   ├── setup_jetson.sh            # 一键环境安装
│   ├── run_all.sh                 # 全系统启动
│   ├── run_voice.sh               # 仅语音模块启动
│   ├── run_vision.sh              # 仅视觉模块启动
│   ├── download_models.sh         # 模型下载
│   ├── monitor_topics.sh          # 话题监控
│   └── clean.sh                   # 清理
└── docs/                          # 文档
    ├── design.md                  # 详细设计
    └── deployment.md              # 部署指南
```

> **详细设计**（模块说明/消息结构/话题一览/性能预期/应用场景）请参阅 [docs/design.md](docs/design.md)  
> **部署指南**（环境要求/安装步骤/启动方式/清理）请参阅 [docs/deployment.md](docs/deployment.md)

## 路线图

- [x] 项目初始化 + Orbbec Astra Pro 驱动集成
- [x] Jetson 远程探测与环境确认
- [x] 软件架构设计 + README 文档
- [x] ROS2 包框架搭建（msg / package.xml / CMakeLists.txt）
- [x] 配置文件体系 (YAML)
- [x] ROS2 launch 启动文件
- [x] 部署/启动/监控脚本
- [ ] 语音采集节点开发 (voice_capture)
- [ ] VAD 节点开发 (voice_vad)
- [ ] ASR 节点开发 - faster-whisper (voice_asr)
- [ ] 图像预处理节点开发 (image_preprocess)
- [ ] YOLOv8 + ONNX Runtime 检测节点开发 (object_detection)
- [ ] 深度处理节点开发 (depth_processor)
- [ ] 多模态融合节点开发 (fusion_node)
- [ ] Jetson 实机部署测试
- [ ] 性能优化 + 代码完善

## 参考资料

- [Orbbec Astra Camera ROS2 Driver](https://github.com/orbbec/ros2_astra_camera)
- [NVIDIA Jetson Orin Nano 官方文档](https://developer.nvidia.com/embedded/learn/jetson)
- [NVIDIA TensorRT 10.7 文档](https://docs.nvidia.com/deeplearning/tensorrt/)
- [YOLOv8 - Ultralytics](https://github.com/ultralytics/ultralytics)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [faster-whisper (CTranslate2)](https://github.com/SYSTRAN/faster-whisper)
- [Vosk Speech Recognition](https://alphacephei.com/vosk/)

## 许可证

本项目基于 Apache License 2.0 开源协议。