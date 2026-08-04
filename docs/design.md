# 详细设计

## 1. 语音采集与识别模块 (Voice Module)

语音模块由以下 ROS2 包组成，位于 `src/voice/` 目录下：

| 包 | 类型 | 说明 |
|----|------|------|
| `voice_capture` | ament_python | ALSA 音频采集（sounddevice） |
| `voice_vad` | ament_python | 能量 VAD 分割音频（前缀缓冲防裁切） |
| `voice_hotword` | ament_python | 双唤醒热词 + Vosk 语法模式匹配 |
| `voice_asr` | ament_python | Whisper 本地转录 (GPU) |
| `voice_feedback` | ament_python | 蜂鸣器/LED 反馈 |
| `voice_doa` | ament_python | 声源定位 |
| `voice_msgs` | ament_cmake | 自定义消息 |

### 架构总览

语音识别分三级流水线，每级开销递增。支持双唤醒词：

```
voice_capture → voice_vad → voice_hotword
                                   │
                    ┌──────────────┼────────────────┐
                    │              │                │
              小车小车唤醒     小方小方唤醒      非唤醒词
                    │              │              │
                    ▼              ▼               ▼
             Vosk语法匹配     ASR直通模式      静默丢弃
             (19短语, CPU)    (直接forward)
                    │              │
         ┌──────────┼──┐           │
         │ 命中     │不匹配         │
         ▼          ▼              ▼
      执行指令  静默等待       Whisper转录
               (不走ASR)           │
                                  ▼
                            asr_result
                              →二次匹配
                              →执行指令
```

| 级别 | 触发条件 | GPU | 延迟 |
|------|---------|-----|------|
| **热词级** | Vosk 语法模式匹配 19 个预定义短语 | ❌ | <50ms |
| **Whisper** | ASR 直通模式（"小方小方"唤醒） → 转录 | ✅ | ~300ms |
| **LLM 云端** | 暂未实现，预留接口 | ❌ | - |

### 目录结构

```
src/voice/
├── voice_capture/          # 音频采集 (不变)
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_capture/
│       └── voice_capture_node.py
├── voice_vad/              # 语音活动检测 (不变)
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_vad/
│       └── voice_vad_node.py
├── voice_hotword/          # 热词匹配 + 指令路由 (新增)
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_hotword/
│       └── voice_hotword_node.py
├── voice_asr/              # Whisper 转录 (精简: 移除唤醒/指令/蜂鸣)
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_asr/
│       └── voice_asr_node.py
├── voice_feedback/         # 蜂鸣器/LED 反馈 (稍改: 订阅 /voice/state)
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_feedback/
│       └── voice_feedback_node.py
├── voice_doa/              # 声源定位 (不变)
│   ├── setup.py / setup.cfg
│   ├── package.xml
│   └── voice_doa/
│       └── voice_doa_node.py
└── voice_msgs/             # 自定义消息 (不变)
    ├── CMakeLists.txt
    ├── package.xml
    └── msg/
        └── VoiceCommand.msg
```

### 1.1 音频采集

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_capture` |
| 输入设备 | ReSpeaker Mic Array v2.0 (XVF3000) |
| ALSA 设备 | `ReSpeaker 4 Mic Array (XFW3000): USB Audio` |
| 采样率 | 16000 Hz (XVF3000 native 48kHz → 内部重采样) |
| 通道 | 1（beamformed mono，XVF3000 硬件输出） |
| 帧长 | 1920 样本（120ms） |
| 板载处理 | 波束成形 + 自适应降噪 + 去混响 |
| Python 依赖 | `sounddevice` |
| 发布话题 | `/voice/audio_raw` (std_msgs/Float32MultiArray) |

**说明：** XVF3000 输出立体声 USB Audio（左 = beamformed mono, 右 = AEC 参考），capture 节点仅取左声道。XVF3000 已做波束成形和降噪，故软件 HPF 默认关闭 (`hp_enable: false`)，如有需要可通过参数开启。

**PulseAudio 兼容：** ReSpeaker 走 PulseAudio 默认输入设备 (`device_index: -1`)，无设备占用冲突，无需停止 PulseAudio。

### 1.2 语音活动检测 (VAD)

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_vad_node` |
| 方法 | 能量 VAD (RMS > 0.02) |
| Python 依赖 | `numpy` |
| 订阅话题 | `/voice/audio_raw` (Float32MultiArray) |
| 发布话题 | `/voice/voice_activity` (std_msgs/Bool) |
| | `/voice/audio_clip` (Float32MultiArray) — 完整语音片段 |

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `sample_rate` | 16000 | 采样率 |
| `frame_ms` | 30 | VAD 帧长 (ms) |
| `silence_timeout` | 0.5 | 静音超时 (秒)，超过后认为语音结束 |
| `prefix_frames` | 10 | 静音前缀缓冲帧数 (~300ms)，防裁切第一个字 |

**工作流程：**
1. 从 `/voice/audio_raw` 接收 PCM 音频帧
2. 每 30ms 帧计算 RMS
3. 维持 **环形前缀缓冲**（最近 10 帧），静默时持续缓存
4. RMS > 0.02 → 说话中，将前缀拼到音频片段开头，缓存音频
5. 静音持续 `silence_timeout` 秒后，发布完整语音片段到 `/voice/audio_clip`

### 1.3 热词匹配 (voice_hotword **新增**)

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_hotword` |
| 引擎 | **Vosk** (Kaldi Grammar 模式，字符空格分隔 + silence吸收) |
| 模型 | `vosk-model-small-cn-0.22` (~42MB, 纯 CPU) |
| Python 依赖 | `vosk`, `numpy` |
| 订阅话题 | `/voice/audio_clip` — VAD 音频段 |
| | `/voice/asr_result` — Whisper 转录文本 (二次匹配) |
| 发布话题 | `/voice/wake` (Bool) — 唤醒状态 |
| | `/voice/voice_command` (VoiceCommand) — 结构化指令 |
| | `/voice/state` (String) — 当前状态 |
| | `/voice/audio_for_asr` (Float32MultiArray) — ASR模式→Whisper |

**双唤醒词：**

| 唤醒词 | 模式 | 蜂鸣 | 说明 |
|--------|------|------|------|
| 小车小车 | Vosk 语法匹配 | 800Hz 单次 | 只匹配 19 个预设短语，不命中则静默忽略 |
| 小方小方 | ASR 直通 | 1000+800Hz 双响 | 跳过 Vosk，每段音频直接发 Whisper 转录 |

**热词表（19 个短语，Vosk Grammar 模式）：**

| 短语 | 动作 | 说明 |
|------|------|------|
| 小车小车 | `wake` | 唤醒 → Vosk 模式 |
| 小方小方 | `wake_asr` | 唤醒 → ASR 直通模式 |
| 前进 / 向前 | `motor: forward` | 直行（支持两种发音） |
| 后退 / 向后 | `motor: backward` | 倒车（支持两种发音） |
| 向左 | `motor: left` | 左平移 |
| 向右 | `motor: right` | 右平移 |
| 左转 | `motor: rotate_left` | 原地左转 |
| 右转 | `motor: rotate_right` | 原地右转 |
| 停止 | `motor: stop` | 停车 |
| 看左边 | `servo: pan_left` | 云台左转 |
| 看右边 | `servo: pan_right` | 云台右转 |
| 回正 | `servo: home` | 云台回中 |
| 过来 / 跟着我 | `follow: start` | 人跟随启动 |
| 回去 | `navigation: return_home` | 回起点 |
| 蜂鸣 | `buzzer: short` | 蜂鸣器短响 |
| 退出 | `deactivate` | 关闭语音，回到休眠（Vosk/ASR 模式均有效） |

**状态机：**

```
SLEEPING ──"小车小车"──→ WAKE (Vosk模式, 蜂鸣800Hz, 5s定时)
SLEEPING ──"小方小方"──→ LISTEN (ASR模式, 蜂鸣1000+800Hz)
WAKE(Vosk) ──指令匹配──→ 执行指令 + 重置5s
WAKE(Vosk) ──无匹配──→ 静默忽略, 重置5s
WAKE(ASR)  ──音频到达──→ 转发Whisper (state=LISTEN)
WAKE(ASR)  ──"退出"──→ SLEEPING
WAKE       ──超时──→ SLEEPING (蜂鸣400Hz)
LISTEN     ──ASR返回──→ WAKE 或 SLEEPING
```

**Epoch 隔离机制：** 每次唤醒递增 `_current_epoch`。ASR 转发时记录当前 epoch，结果返回时校验 epoch 是否匹配，不匹配则丢弃（避免前一轮的慢 ASR 结果污染当前状态）。

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `sample_rate` | 16000 | 采样率 |
| `vosk_model_path` | `~/vosk-model-small-cn-0.22` | Vosk 模型路径 |
| `wake_timeout` | 5.0 | 唤醒超时 (秒) |
| `clip_save_dir` | `/tmp/vosk_clips` | 调试音频保存路径 |
| `clip_save_enabled` | false | 是否保存调试音频 |
| `wake_buzzer_freq` | 800 | 唤醒蜂鸣频率 |
| `wake_buzzer_duration` | 0.1 | 唤醒蜂鸣时长 |

### 1.4 语音识别 (voice_asr **精简**)

**变更：** 移除唤醒逻辑、指令解析（关键词左转/右转/前进等）、buzzer/servo 发布，仅保留 Whisper 转录功能。

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_asr` |
| 引擎 | **openai-whisper** (PyTorch, GPU 加速) |
| 模型 | `base`（推荐）/ `tiny` / `small` |
| 设备 | CUDA (GPU: Orin Nano) |
| Python 依赖 | `openai-whisper`, `opencc`, `scipy` |
| 订阅话题 | `/voice/audio_for_asr` (Float32MultiArray) — 仅唤醒态下转发 |
| | `/voice/wake` (Bool) — 门控信号：仅 WAKE=true 时激活 |
| 发布话题 | `/voice/asr_result` (std_msgs/String) — 转录文本 |

**参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `model_size` | base | tiny / base / small |
| `device` | cuda | cuda / cpu |
| `language` | zh | 语言代码 |
| `sample_rate` | 16000 | 音频采样率 |
| `hp_cutoff` | 300 | 高通滤波，去除风扇噪声 |

**性能 (Jetson Orin Nano GPU)：**

| 模型 | 推理时间 (3s 音频) | 显存占用 |
|------|-------------------|---------|
| tiny | ~0.3s | ~500MB |
| base | ~0.5s | ~800MB |
| small | ~1.5s | ~1.5GB |

### 1.5 ament_python 构建注意事项

语音包均为 `ament_python` 类型。ROS2 的 `ros2 run` 和 `ros2 launch` 在 `<prefix>/lib/<包名>/` 下查找可执行文件，但 colcon 的 `setup.py develop` 模式将 console_scripts 安装到 `bin/` 目录。

**解决方案：** 每个包根目录添加 `setup.cfg`：

```ini
[develop]
script_dir=$base/lib/voice_capture
```

此配置将 develop 模式的脚本安装目录重定向到 `lib/<包名>/`，使 `ros2 run` 能正常找到可执行文件。

### 1.6 DOA 声源定位 (voice_doa)

| 项目 | 说明 |
|------|------|
| 节点名 | `voice_doa` |
| 硬件 | ReSpeaker v2.0 XVF3000 HID 接口 |
| Python 依赖 | `hidapi` (pip) + `libhidapi-libusb0` (系统) |
| USB VID:PID | `0x2886:0x0018` (Seeed) |
| DOA 精度 | 30° 扇区 (0-11) |
| 发布话题 | `/voice/doa_angle` (std_msgs/Float32) — 角度 0-360° |
| | `/voice/doa_direction` (std_msgs/String) — 方向标签 |

**数据流：**

```
XVF3000 USB HID → hidapi/hidraw → voice_doa_node → /voice/doa_angle
                                                        ↓
                                              servo_tracker_node
                                                        ↓
                                              /servo_controller
                                                        ↓
                                              Pi3 STM32 舵机云台
```

### 1.7 声源跟踪 (servo_tracker)

| 项目 | 说明 |
|------|------|
| 节点名 | `servo_tracker` |
| 包 | `jetauto_app` |
| 订阅 | `/voice/doa_angle` (Float32)、`/voice/doa_locked` (Float32)、`/voice/vad_hw` (Bool)、`/voice/wake` (Bool) |
| 发布 | `/servo_controller` (ServosPosition)、`/cmd_vel` (Twist) |
| 触发 | **仅唤醒事件**（`/voice/wake=True`）。移动指令（前进/左转等）不再触发舵机/旋转 |
| 方向数据 | 优先 VAD 上升沿锁存值（`/voice/doa_locked`，唤醒词方向）；无锁存时兜底 vad=True 期间的 DOA；无语音时 DOA 为漂移噪声，不采信 |
| 行为 | DOA 在 ±45° 内 → 只转舵机对准；超出 ±45° → **开环整体旋转**（最短转角 ÷ rotate_gain 换算时长，转完即停，舵机不动） |
| 回正 | 退出/自动休眠（`/voice/wake=False`）→ 舵机回正 center_pulse(500)、停止旋转 |
| 校准 | DOA 为小车坐标系 0-360°（正前=0/右=90/左=270/后=180），由 voice_doa `angle_offset=270` 镜像换算（拾音器递增方向与小车相反） |
| 参数 | `invert=true`、`rotate_gain=0.6`（唤醒旋转速度加倍）、`chase_timeout=10.0`（开环旋转时长上限） |

### 1.8 启动流程

1. `voice_capture_node` 启动音频流，发布原始音频帧
2. `voice_vad_node` 接收音频帧，能量 VAD 检测（前缀缓冲防裁切），切出语音段
3. `voice_hotword_node` 接收音频段 → Vosk Grammar 模式匹配
   - 匹配"小车小车" → 唤醒，Vosk 语法模式，蜂鸣800Hz，5s超时
   - 匹配"小方小方" → 唤醒，ASR直通模式，蜂鸣1000+800Hz
   - 匹配"退出" → 回到休眠（两种模式均有效）
   - Vosk 模式下匹配其他热词 → 直接发布指令
   - Vosk 模式下无匹配 → 静默忽略（不走ASR兜底）
   - ASR 模式下音频到达 → 直接转发 `voice_asr_node`
4. `voice_asr_node` 接收音频 → Whisper 转录 → 回传给 hotword 做文本二次匹配
5. `voice_feedback_node` 订阅 `/voice/state`，根据状态输出蜂鸣/LED

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

| 话题 | 类型 | 发布者 | 消费者 | 说明 |
|------|------|--------|--------|------|
| `/voice/audio_raw` | `Float32MultiArray` | voice_capture | voice_vad | 16kHz PCM音频帧 |
| `/voice/voice_activity` | `std_msgs/Bool` | voice_vad | hotword | 语音活动标志 |
| `/voice/audio_clip` | `Float32MultiArray` | voice_vad | hotword | 完整语音片段 |
| `/voice/wake` | `std_msgs/Bool` | hotword | asr, feedback, doa | 唤醒状态 |
| `/voice/state` | `std_msgs/String` | hotword | feedback | 状态：sleeping/wake/listen |
| `/voice/audio_for_asr` | `Float32MultiArray` | hotword | asr | 未匹配音频 → Whisper |
| `/voice/asr_result` | `std_msgs/String` | asr | hotword | 转录文本（回传热词节点做二次匹配） |
| `/voice/voice_command` | `VoiceCommand` | hotword | fusion/controller | 结构化指令（最终输出） |
| `/voice/doa_angle` | `std_msgs/Float32` | voice_doa | tracker | 声源方向角度 (0-360°) |
| `/voice/doa_direction` | `std_msgs/String` | voice_doa | - | 声源方向标签 |
| `/voice/vad_hw` | `std_msgs/Bool` | voice_doa | - | 硬件 VAD 状态 (XVF3000) |
| `/voice/status_led` | `std_msgs/ColorRGBA` | voice_feedback | voice_doa sub | LED 灯环颜色控制 |
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
| 热词匹配 (Vosk NFST) | <50ms | 实时 | 纯 CPU，15 短语一次性推理 |
| 语音识别 (Whisper tiny) | ~300ms | - | openai-whisper on CUDA, 仅唤醒态下触发 |
| 语音识别 (Whisper base) | ~500ms | - | 精度更高 |
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
