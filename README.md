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

## 实测环境信息（2026-05-31）

以下信息通过 SSH 连接至 Jetson 设备 `192.168.3.78` 采集获取：

| 项目 | 版本/型号 |
|------|----------|
| JetPack | **R36.5.0** (L4T 36.5.0) |
| 系统 | Ubuntu **22.04.5 LTS** (Jammy) |
| 内核 | Linux 5.15.185-tegra aarch64 |
| CUDA | **12.6.11** (安装在 `/usr/local/cuda-12.6`) |
| TensorRT | **10.7.0.23** |
| ROS2 | **Humble** (`/opt/ros/humble`) |
| Python | 3.10.12 |
| PyTorch | **2.5.0a0+nv24.08** (NVIDIA JetPack 优化版) |
| OpenCV | **4.10.0** |
| ONNX Runtime | **1.20.0** |
| jetson_utils | 已安装 |
| jtop | 4.3.2（已安装） |
| sounddevice | **0.5.5**（已安装） |

> **注意：** `nvcc` 不直接存在于系统 PATH 中，但 CUDA 工具链在 `/usr/local/cuda-12.6/bin` 下可用，可通过完整路径调用或手动加入 PATH。`pyaudio` 库未安装（若需使用可 `pip install pyaudio`）。此开发板型号被识别为 **NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super**。

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
│  │  └──────▼────┘      │    │  ┌────────▼──────────────┐ │  │
│  │         │            │    │  │ 深度处理节点           │ │  │
│  │         │            │    │  │ (点云/距离测量)        │ │  │
│  │  ┌──────▼──────────┐ │    │  └────────┬──────────────┘ │  │
│  │  │  决策/融合节点    │ │    └───────────┼──────────────┘  │
│  │  │  (多模态融合)     │◄─┼────────────────┘                │
│  │  └──────┬──────────┘ │                                  │
│  │         │            │                                  │
│  │  ┌──────▼──────────┐ │                                  │
│  │  │  应用层          │ │                                  │
│  │  │  (控制/显示/交互) │ │                                  │
│  │  └─────────────────┘ │                                  │
│  └──────────────────────┘                                  │
│                                                              │
│  ════════════════════════════════════════════════════════    │
│  底层: ROS2 Humble + CUDA 12.6 + TensorRT 10.7 + Python 3.10│
└──────────────────────────────────────────────────────────────┘
```

## 模块详细设计

### 1. 语音采集与识别模块 (Voice Module)

#### 1.1 音频采集
- **输入设备：** Orbbec Astra Pro 内置麦克风
  - ALSA card: `card 0: Pro [ASTRA Pro], device 0: USB Audio [USB Audio]`
  - 设备路径：`plughw:0,0` 或 `hw:0,0`
- **采样率：** 16kHz（语音识别推荐采样率）
- **ROS2 节点：** `voice_capture_node`
  - 发布话题：`/voice/audio_raw` (audio_msgs/AudioData)
  - 帧长：1600 样本/帧（100ms）
  - Python 依赖：`sounddevice` (已安装 0.5.5) 或 `pyaudio`

#### 1.2 语音活动检测 (VAD)
- **方法：** WebRTC VAD 或 Silero VAD
- **ROS2 节点：** `voice_vad_node`
  - 订阅：`/voice/audio_raw`
  - 发布：`/voice/voice_activity` (std_msgs/Bool)
  - 检测到人声开始后缓存音频，静音超限后触发识别

#### 1.3 语音识别 (ASR)
- **离线方案优先**（Jetson 边缘场景、无网环境）
- **推荐方案：**

| 方案 | 模型大小 | GPU加速 | 适用性 |
|------|----------|---------|--------|
| **Whisper tiny** (首选) | ~150MB | ✅ TensorRT | 开源、多语言、Jetson 上已有 PyTorch 2.5 支持 |
| **Whisper base** | ~300MB | ✅ TensorRT | 精度更高 |
| **Vosk** | ~50MB | ❌ CPU | 轻量、适合简单命令词 |

- **ROS2 节点：** `voice_asr_node`
  - 订阅：`/voice/audio_clip` (完整音频片段)
  - 发布：`/voice/asr_result` (std_msgs/String)
  - 推荐使用：Whisper tiny 通过 ONNX → TensorRT 加速

### 2. 图像采集与识别模块 (Vision Module)

#### 2.1 相机驱动
- **驱动：** `ros2_astra_camera`（已作为 submodule 集成在 `src/orbbec_ws/`）
- **USB 设备 ID：** `2bc5:0403 Astra Pro` + `2bc5:0501 Astra Pro HD Camera`
- **发布话题：**
  - `/camera/color/image_raw` — RGB 图像
  - `/camera/depth/image_raw` — 深度图像
  - `/camera/ir/image_raw` — 红外图像
  - `/camera/color/camera_info` — RGB 相机标定参数
  - `/camera/depth/camera_info` — 深度相机标定参数
- **挂载方式：** `astra.launch.xml` 启动

#### 2.2 图像预处理
- **ROS2 节点：** `image_preprocess_node`
  - 订阅：`/camera/color/image_raw`
  - 输出：resize + normalize + tensor 格式转换
  - 发布：`/vision/preprocessed_image`

#### 2.3 目标检测与识别
- **推理引擎：** NVIDIA TensorRT 10.7（.engine 格式） + Jetson CUDA 12.6
- **推荐模型：**

| 模型 | 大小 | FPS (TensorRT FP16) | 说明 |
|------|------|---------------------|------|
| **YOLOv8n** | ~6MB | 200+ | 轻量、实时性最好 |
| **YOLOv8s** | ~22MB | 150+ | 精度与速度平衡 |
| **YOLOv5n** | ~4MB | 250+ | 最轻量 |

- **ROS2 节点：** `object_detection_node`
  - 订阅：`/vision/preprocessed_image`
  - 发布：`/vision/detection_result` (自定义 `Detection2DArray`)
  - 发布：`/vision/detected_image` (可视化检测结果)

#### 2.4 深度处理
- **ROS2 节点：** `depth_processor_node`
  - 订阅：`/camera/depth/image_raw`
  - 功能：目标距离估算（结合检测框 ROI 取深度中值）
  - 发布：`/vision/distance_result`

### 3. 多模态融合模块

- **ROS2 节点：** `fusion_node`
  - 融合语音指令和视觉检测结果
  - 示例场景：
    - 语音"前方有什么？" → 返回当前检测到的物体列表
    - 语音"杯子在哪里？" → 融合 NLP 意图 + 视觉检测 → 返回物体位置和距离
  - 发布：`/fusion/command` — 结构化指令结果

## 项目目录结构

```
HiJetson/
├── README.md                      # 本文件
├── .gitmodules                    # submodule 配置
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
│       ├── hijetson_all.launch.py # 全系统启动（语音+视觉+融合）
│       ├── hijetson_voice.launch.py # 仅启动语音模块
│       └── hijetson_vision.launch.py # 仅启动视觉模块
├── scripts/                       # 工具脚本
│   ├── setup_jetson.sh            # Jetson 一键环境安装脚本
│   ├── run_all.sh                 # 全系统启动 (Jetson)
│   ├── run_voice.sh               # 仅启动语音模块
│   ├── run_vision.sh              # 仅启动视觉模块
│   ├── download_models.sh         # YOLOv8 + Whisper 模型下载
│   ├── monitor_topics.sh          # ROS2 话题实时监控
│   └── clean.sh                   # 清理编译产物
└── docs/                          # 文档
    ├── hardware_setup.md          # 硬件搭建指南
    ├── jetson_setup.md            # Jetson 环境配置
    └── usage_guide.md             # 使用指南
```

## ROS2 消息结构

```yaml
# voice_msgs/VoiceCommand.msg
string command_text           # 识别的文本
float32 confidence            # 识别置信度 (0~1)
string[] keywords             # 提取的关键词
builtin_interfaces/Time timestamp

# vision_msgs/Detection2D.msg
string label                  # 类别名称
float32 confidence            # 检测置信度
float32 x                     # 检测框中心 x (归一化 0~1)
float32 y                     # 检测框中心 y (归一化 0~1)
float32 width                 # 检测框宽 (归一化 0~1)
float32 height                # 检测框高 (归一化 0~1)

# vision_msgs/Detection2DArray.msg
VisionInfo vision_info
vision_msgs/Detection2D[] detections

# vision_msgs/VisionInfo.msg
uint32 image_width
uint32 image_height
string encoding
builtin_interfaces/Time timestamp

# fusion_msgs/FusedResult.msg
string[] detected_objects     # 检测到的物体列表
float32[] distances           # 对应的距离 (米)
string voice_command          # 语音指令原文
string intent                 # 解析的意图
builtin_interfaces/Time timestamp
```

## 部署指南

### 前提条件

| 软件 | 版本 | 说明 |
|------|------|------|
| JetPack | **R36.5.0** (L4T 36.5.0) | 已安装在 Jetson |
| ROS2 | **Humble** | `/opt/ros/humble` |
| CUDA | **12.6.11** | `/usr/local/cuda-12.6` |
| TensorRT | **10.7.0.23** | 已安装 |
| Python | **3.10.12** | 已安装 |
| PyTorch | **2.5.0a0+nv24.08** | JetPack 优化版 |
| OpenCV | **4.10.0** | 已安装 |

### 一键安装（Jetson Orin Nano）

首次部署运行安装脚本，自动完成所有依赖安装：

```bash
# 克隆项目
git clone https://github.com/ahlijin/HiJetson.git
cd HiJetson
git submodule update --init --recursive

# 一键安装（系统依赖、ROS2、Python包、驱动、模型、编译）
sudo chmod +x scripts/setup_jetson.sh
./scripts/setup_jetson.sh

# 设置 USB 设备权限
cd src/orbbec_ws/astra_camera/scripts
sudo bash install.sh
sudo udevadm control --reload-rules && sudo udevadm trigger
cd ../../..
```

### 手动部署步骤

```bash
# 1. 编译 Orbbec 相机驱动
cd src/orbbec_ws
source /opt/ros/humble/setup.bash
colcon build --event-handlers console_direct+ --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
cd ../..

# 2. 安装设备权限
cd src/orbbec_ws/astra_camera/scripts
sudo bash install.sh
sudo udevadm control --reload-rules && sudo udevadm trigger
cd ../../..

# 3. 编译 HiJetson 工作空间
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash

# 4. 下载 AI 模型
./scripts/download_models.sh

# 5. 启动系统
./scripts/run_all.sh
```

## 启动方式

### 全系统启动

```bash
./scripts/run_all.sh
```

或使用 ROS2 launch:

```bash
ros2 launch src/launch/hijetson_all.launch.py
```

### 仅启动语音模块（测试语音识别）

```bash
./scripts/run_voice.sh
```

### 仅启动视觉模块（测试目标检测）

```bash
./scripts/run_vision.sh
```

### 系统监控

```bash
# 查看实时话题数据
./scripts/monitor_topics.sh

# 手动查看语音命令输出
ros2 topic echo /voice/voice_command

# 手动查看检测结果
ros2 topic echo /vision/detection_result

# 手动查看融合结果
ros2 topic echo /fusion/result
```

### 停止系统

```bash
# 按 Ctrl+C 即可优雅停止所有节点
```

## 性能预期

| 模块 | 延迟 | 帧率/FPS | 备注 |
|------|------|----------|------|
| 语音识别 (Whisper tiny) | ~300-500ms | - | faster-whisper on GPU, 单次指令 |
| 语音识别 (Whisper base) | ~500-800ms | - | 精度更高，适合中英文混合 |
| 目标检测 (YOLOv8n ONNX) | ~10-15ms | ~60-80 FPS | 640×480 输入，GPU 运行 |
| 目标检测 (YOLOv8s ONNX) | ~15-25ms | ~40-60 FPS | 640×480 输入 |
| 深度图获取 | - | 30 FPS | 硬件直接输出 |
| 彩色图获取 | - | 30 FPS | 硬件直接输出 |
| VAD 活动检测 | ~10ms | 实时 | 100ms 帧处理 |

## 应用场景

1. **智能机器人视觉导航**
   - 语音指令控制 → 视觉识别目标 → 深度测距 → 路径规划
2. **智能语音交互终端**
   - 语音唤醒 → 人脸识别 → 语音对话
3. **边缘安防监控**
   - 语音异常检测 + 目标检测 + 实时告警
4. **物体抓取系统**
   - 语音"抓取红色杯子" → YOLO 检测杯子 → 深度定位 → 机械臂控制

## ROS2 消息话题一览

| 话题 | 类型 | 发布者 | 说明 |
|------|------|--------|------|
| `/voice/audio_raw` | `audio_msgs/AudioData` | voice_capture | 16kHz PCM音频帧 |
| `/voice/voice_activity` | `std_msgs/Bool` | voice_vad | 语音活动标志 |
| `/voice/audio_clip` | `audio_msgs/AudioData` | voice_vad | 完整语音片段 |
| `/voice/asr_result` | `std_msgs/String` | voice_asr | ASR识别文本 |
| `/voice/voice_command` | `VoiceCommand` | voice_asr | 结构化语音指令 |
| `/camera/color/image_raw` | `sensor_msgs/Image` | astra_camera | RGB彩色图 |
| `/camera/depth/image_raw` | `sensor_msgs/Image` | astra_camera | 深度图 |
| `/vision/preprocessed_image` | `sensor_msgs/Image` | image_preprocess | 预处理后图像 |
| `/vision/detection_result` | `Detection2DArray` | object_detection | 检测结果数组 |
| `/vision/detected_image` | `sensor_msgs/Image` | object_detection | 可视化检测图 |
| `/vision/distance_result` | `Float32MultiArray` | depth_processor | 目标距离 |
| `/fusion/result` | `FusedResult` | fusion_node | 多模态融合结果 |

## 清理

```bash
# 清理编译产物
./scripts/clean.sh

# 清理全部（包括模型文件）
./scripts/clean.sh --all
```

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