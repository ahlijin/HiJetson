# 详细设计

## 1. 语音采集与识别模块 (Voice Module)

### 1.1 音频采集
- **输入设备：** Orbbec Astra Pro 内置麦克风
  - ALSA card: `card 0: Pro [ASTRA Pro], device 0: USB Audio [USB Audio]`
  - 设备路径：`plughw:0,0` 或 `hw:0,0`
- **采样率：** 16kHz（语音识别推荐采样率）
- **ROS2 节点：** `voice_capture_node`
  - 发布话题：`/voice/audio_raw` (audio_msgs/AudioData)
  - 帧长：1600 样本/帧（100ms）
  - Python 依赖：`sounddevice` (已安装 0.5.5) 或 `pyaudio`

### 1.2 语音活动检测 (VAD)
- **方法：** WebRTC VAD 或 Silero VAD
- **ROS2 节点：** `voice_vad_node`
  - 订阅：`/voice/audio_raw`
  - 发布：`/voice/voice_activity` (std_msgs/Bool)
  - 检测到人声开始后缓存音频，静音超限后触发识别

### 1.3 语音识别 (ASR)
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

## 2. 图像采集与识别模块 (Vision Module)

### 2.1 相机驱动
- **驱动：** `ros2_astra_camera`（已作为 submodule 集成在 `src/orbbec_ws/`）
- **USB 设备 ID：** `2bc5:0403 Astra Pro` + `2bc5:0501 Astra Pro HD Camera`
- **发布话题：**
  - `/camera/color/image_raw` — RGB 图像
  - `/camera/depth/image_raw` — 深度图像
  - `/camera/ir/image_raw` — 红外图像
  - `/camera/color/camera_info` — RGB 相机标定参数
  - `/camera/depth/camera_info` — 深度相机标定参数
- **挂载方式：** `astra.launch.xml` 启动

### 2.2 图像预处理
- **ROS2 节点：** `image_preprocess_node`
  - 订阅：`/camera/color/image_raw`
  - 输出：resize + normalize + tensor 格式转换
  - 发布：`/vision/preprocessed_image`

### 2.3 目标检测与识别
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

### 2.4 深度处理
- **ROS2 节点：** `depth_processor_node`
  - 订阅：`/camera/depth/image_raw`
  - 功能：目标距离估算（结合检测框 ROI 取深度中值）
  - 发布：`/vision/distance_result`

## 3. 多模态融合模块

- **ROS2 节点：** `fusion_node`
  - 融合语音指令和视觉检测结果
  - 示例场景：
    - 语音"前方有什么？" → 返回当前检测到的物体列表
    - 语音"杯子在哪里？" → 融合 NLP 意图 + 视觉检测 → 返回物体位置和距离
  - 发布：`/fusion/command` — 结构化指令结果

## 4. ROS2 消息结构

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

## 5. ROS2 消息话题一览

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

## 6. 性能预期

| 模块 | 延迟 | 帧率/FPS | 备注 |
|------|------|----------|------|
| 语音识别 (Whisper tiny) | ~300-500ms | - | faster-whisper on GPU, 单次指令 |
| 语音识别 (Whisper base) | ~500-800ms | - | 精度更高，适合中英文混合 |
| 目标检测 (YOLOv8n ONNX) | ~10-15ms | ~60-80 FPS | 640×480 输入，GPU 运行 |
| 目标检测 (YOLOv8s ONNX) | ~15-25ms | ~40-60 FPS | 640×480 输入 |
| 深度图获取 | - | 30 FPS | 硬件直接输出 |
| 彩色图获取 | - | 30 FPS | 硬件直接输出 |
| VAD 活动检测 | ~10ms | 实时 | 100ms 帧处理 |

## 7. 应用场景

1. **智能机器人视觉导航**
   - 语音指令控制 → 视觉识别目标 → 深度测距 → 路径规划
2. **智能语音交互终端**
   - 语音唤醒 → 人脸识别 → 语音对话
3. **边缘安防监控**
   - 语音异常检测 + 目标检测 + 实时告警
4. **物体抓取系统**
   - 语音"抓取红色杯子" → YOLO 检测杯子 → 深度定位 → 机械臂控制