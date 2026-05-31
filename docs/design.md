# 详细设计

## 1. 语音采集与识别模块 (Voice Module)

语音模块由四个 ROS2 包组成，位于 `src/voice/` 目录下。

### 目录结构

```
src/voice/
├── voice_capture/          # 音频采集
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_capture/
│       └── voice_capture_node.py
├── voice_vad/              # 语音活动检测
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_vad/
│       └── voice_vad_node.py
├── voice_asr/              # 语音识别
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_asr/
│       └── voice_asr_node.py
└── voice_msgs/             # 自定义消息
    ├── CMakeLists.txt
    ├── package.xml
    └── msg/
        └── VoiceCommand.msg
```

### 1.1 音频采集

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_capture` |
| 输入设备 | Orbbec Astra Pro 内置麦克风 |
| ALSA 设备 | `card 0: Pro [ASTRA Pro], device 0: USB Audio` |
| 采样率 | 16000 Hz |
| 通道 | 2（立体声），自动混音为单声道 |
| 帧长 | 1600 样本（100ms） |
| Python 依赖 | `sounddevice` |
| 发布话题 | `/voice/audio_raw` (std_msgs/Float32MultiArray) |

**注意：** ASTRA Pro 为 2 通道 USB 音频设备。使用 ALSA 直通（`device=0`）时必须指定 `channels=2`，代码内部自动将双通道混音为单声道后发布。

**PulseAudio 冲突：** Jetson 上 PulseAudio 默认占用 USB 音频设备，导致 sounddevice 无法通过 ALSA 直通（`hw:0,0`）访问。需要在启动前临时停止 PulseAudio。

```bash
systemctl --user stop pulseaudio.service pulseaudio.socket
```

### 1.2 语音活动检测 (VAD)

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_vad` |
| 方法 | WebRTC VAD |
| Python 依赖 | `webrtcvad` |
| 订阅话题 | `/voice/audio_raw` (Float32MultiArray) |
| 发布话题 | `/voice/voice_activity` (std_msgs/Bool) — 是否正在说话 |
| | `/voice/audio_clip` (Float32MultiArray) — 完整语音片段 |

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `sample_rate` | 16000 | 采样率 |
| `frame_ms` | 30 | VAD 帧长 (ms)，webrtcvad 要求 30ms |
| `silence_timeout` | 0.5 | 静音超时 (秒)，超过后认为语音结束 |
| `vad_mode` | 1 | 敏感度 0-3，3 最严格 |

**工作流程：**
1. 从 `/voice/audio_raw` 接收 PCM 音频帧
2. 将 float32 转为 int16 PCM（webrtcvad 要求）
3. 每 30ms 帧执行 VAD 检测
4. 检测到语音开始后缓存音频
5. 静音持续 `silence_timeout` 秒后，发布完整语音片段
6. 实时推送 `/voice/voice_activity` 状态

### 1.3 语音识别 (ASR)

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_asr` |
| 引擎 | **openai-whisper** (PyTorch, GPU 加速) |
| 模型 | `tiny`（默认）/ `base` / `small` |
| 设备 | CUDA (GPU: Orin) |
| Python 依赖 | `openai-whisper`, `numba` |
| 订阅话题 | `/voice/audio_clip` (Float32MultiArray) |
| 发布话题 | `/voice/asr_result` (std_msgs/String) — 识别文本 |
| | `/voice/voice_command` (voice_msgs/VoiceCommand) — 结构化指令 |

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `model_size` | tiny | tiny / base / small / medium / large |
| `device` | cuda | cuda / cpu |
| `language` | zh | 语言代码（zh=en, zh=Chinese） |
| `sample_rate` | 16000 | 音频采样率 |

**性能 (Jetson Orin Nano GPU):**

| 模型 | 推理时间 (3s 音频) | 显存占用 |
|------|-------------------|---------|
| tiny | ~0.3s | ~500MB |
| base | ~0.5s | ~800MB |
| small | ~1.5s | ~1.5GB |

**已知问题：**

- `numba` 与高版本 `coverage` 不兼容，如遇 `AttributeError: module 'coverage' has no attribute 'types'`，降级 coverage：
  ```bash
  pip install "coverage==6.5.0"
  ```
- ctranslate2 (faster-whisper) 在 Jetson aarch64 上无 CUDA 支持的预编译 wheel，如需使用需从源码编译。

### 1.4 ament_python 构建注意事项

语音包均为 `ament_python` 类型。ROS2 的 `ros2 run` 和 `ros2 launch` 在 `<prefix>/lib/<包名>/` 下查找可执行文件，但 colcon 的 `setup.py develop` 模式将 console_scripts 安装到 `bin/` 目录。

**解决方案：** 每个包根目录添加 `setup.cfg`：

```ini
[develop]
script_dir=$base/lib/voice_capture
```

此配置将 develop 模式的脚本安装目录重定向到 `lib/<包名>/`，使 `ros2 run` 能正常找到可执行文件。

### 1.5 启动流程

1. `voice_capture_node` 启动音频流，发布原始音频帧
2. `voice_vad_node` 接收音频帧，进行 VAD 检测
3. VAD 检测到完整语音片段后发布到 `/voice/audio_clip`
4. `voice_asr_node` 接收音频片段，使用 Whisper 进行 ASR
5. 识别文本发布到 `/voice/asr_result` 和 `/voice/voice_command`

```bash
# 启动所有语音节点
ros2 launch src/launch/hijetson_voice.launch.py

# 查看识别结果
ros2 topic echo /voice/asr_result
```

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
| `/voice/audio_raw` | `Float32MultiArray` | voice_capture | 16kHz PCM音频帧 |
| `/voice/voice_activity` | `std_msgs/Bool` | voice_vad | 语音活动标志 |
| `/voice/audio_clip` | `Float32MultiArray` | voice_vad | 完整语音片段 |
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
| 语音识别 (Whisper tiny) | ~300ms | - | openai-whisper on CUDA, 单次指令 |
| 语音识别 (Whisper base) | ~500ms | - | 精度更高，适合中英文混合 |
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
