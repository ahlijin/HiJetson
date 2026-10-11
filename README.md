# HiJetson — Jetson Orin Nano × Orbbec Astra Pro + ReSpeaker 多模态感知系统

HiJetson 是 HiWonder JetAuto 双机方案的**上层感知端**：运行在 **NVIDIA Jetson Orin Nano 8G** 上，配合 **Orbbec Astra Pro** 深度相机与 **ReSpeaker Mic Array v2.0（XVF3000）** 麦克风阵列，完成语音交互与视觉感知。底盘运动控制（Pi3 侧）代码在姊妹仓库 **HiWonder_JetAuto**。

- **语音**：采集 → XVF3000 硬件 VAD 切分 → Vosk 双唤醒热词 → Whisper 转录 → 指令执行（电机 / 舵机 / 蜂鸣 / LED），并带 XVF3000 声源定位（DOA）舵机跟随
- **视觉**：Astra Pro 驱动与深度处理已接入；图像预处理 / YOLO 目标检测 / 多模态融合**尚未实现**
- **双机协同**：与 Pi3 通过 ROS2 DDS 协同（`ROS_DOMAIN_ID=42`），Jetson 侧下发 `/cmd_vel`、`/servo_controller`，Pi3 侧回传 `/odom`、`/scan`

## 硬件平台

| 组件 | 型号 | 说明 |
|------|------|------|
| 核心计算平台 | NVIDIA Jetson Orin Nano 8GB | Ampere GPU (1024 CUDA cores, 32 Tensor Cores), 6核 ARM Cortex-A78AE CPU, 40 TOPS AI算力 |
| 深度相机 | Orbbec Astra Pro | RGB 1080P + Depth 640×480 + IR，支持结构光深度感知 |
| 麦克风阵列 | ReSpeaker Mic Array v2.0 (XVF3000) | USB Audio，板载波束成形 + 降噪 + 去混响，硬件 VAD 与声源定位（DOA） |
| 底盘控制板 | STM32（经 Pi3 转发） | 总线舵机 / 蜂鸣器 / LED 灯环，经 `ros_robot_controller_msgs` 访问 |
| 底盘 | HiWonder JetAuto（Mecanum） | 底层运动控制在 Pi3，见 HiWonder_JetAuto 仓库 |
| 存储 | NVMe SSD 233GB | `/dev/nvme0n1p1` |

## 环境软件栈

| 项目 | 版本 |
|------|------|
| JetPack | **R36.5.0** (L4T 36.5.0) |
| 系统 | Ubuntu **22.04.5 LTS** (Jammy) |
| CUDA | **12.6.11** |
| TensorRT | **10.7.0.23** |
| ROS2 | **Humble** (`ROS_DOMAIN_ID=42`) |
| Python | 3.10.12 |
| PyTorch | **2.5.0a0+nv24.08** (NVIDIA JetPack 优化版) |
| OpenCV | **4.10.0** |
| Whisper | **openai-whisper**（`base` 模型，PyTorch CUDA） |
| sounddevice | **0.5.5** |
| Vosk | **vosk-model-small-cn-0.22**（中文小模型，CPU，唤醒热词） |
| pyusb | ReSpeaker 声源定位（DOA）后端，不 detach ALSA 驱动 |

> 唤醒词检测用的是 **Vosk 热词（语法模式匹配）**，不是 OpenWakeWord；OpenWakeWord 已从方案中移除。

## 软件架构

### 语音识别与指令执行链路

```
voice_capture ──/voice/audio_raw──┐
                                  ├─► voice_vad ──/voice/audio_clip──► voice_hotword
voice_doa ──/voice/vad_hw─────────┘        └─/voice/voice_activity
   (XVF3000 硬件 VAD)                                              │
                          ┌───────────────────────────────────────┤
         "小车小车" → Vosk 短语匹配(19 条, CPU)          "小方小方" → ASR 直通
                          │                                       │
              /voice/voice_command                  /voice/audio_for_asr
                          │                                       │
                          ▼                                       ▼
                  voice_executor                            voice_asr (Whisper CUDA)
                          │                                       │
      ┌───────────────────┼───────────────────┐           /voice/asr_result
      ▼                   ▼                   ▼                   │
  /cmd_vel        /servo_controller   set_buzzer / status_led ◄──二次匹配执行
  (Twist)         (ServosPosition)          (蜂鸣器 / LED)
```

- **小车小车**：唤醒后走 Vosk 语法匹配，命中预设短语直接执行，不消耗 Whisper GPU
- **小方小方**：唤醒后走 ASR 直通，任意内容交给 Whisper 转录，转录结果二次匹配后执行
- 二者都有 `wake_timeout`（默认 5s）；说 **退出** 回到休眠

### 声源定位与舵机跟随

```
XVF3000 DOA (pyusb 直读, 不 detach ALSA) → voice_doa
   ├─ /voice/vad_hw         (Bool)    硬件 VAD 状态，供 voice_vad 门控
   ├─ /voice/doa_angle      (Float32) 校准后小车坐标系角度 (正前=0/右=90/左=270/后=180)
   ├─ /voice/doa_locked     (Float32) VAD 上升沿锁存的 DOA（无语音时 DOA 是漂移噪声，不可信）
   └─ /voice/doa_direction  (String)  方向文本
        → jetauto_app/servo_tracker
             ├─ 声源在舵机 ±45° 内：转舵机     → /servo_controller
             └─ 超出范围：开环整车旋转到朝向   → /cmd_vel
```

## 语音模块（`src/voice/`）

| 包 | 类型 | 说明 | 关键话题 |
|----|------|------|----------|
| `voice_capture` | ament_python | 音频采集（sounddevice，16kHz 单声道，默认 PulseAudio 默认输入） | pub `/voice/audio_raw` |
| `voice_doa` | ament_python | XVF3000 声源定位 + 硬件 VAD 转发（pyusb 后端） | pub `/voice/vad_hw`、`/voice/doa_angle`、`/voice/doa_locked`、`/voice/doa_direction` |
| `voice_vad` | ament_python | 基于硬件 VAD 的语音段切分（含前缀缓冲防裁切） | sub `/voice/audio_raw`、`/voice/vad_hw`；pub `/voice/audio_clip`、`/voice/voice_activity` |
| `voice_hotword` | ament_python | 双唤醒热词 + Vosk 短语匹配 + 指令派发 | sub `/voice/audio_clip`、`/voice/asr_result`；pub `/voice/wake`、`/voice/voice_command`、`/voice/state`、`/voice/audio_for_asr` |
| `voice_asr` | ament_python | Whisper 本地转录（`base` / CUDA / 中文） | sub `/voice/audio_for_asr`、`/voice/wake`；pub `/voice/asr_result` |
| `voice_executor` | ament_python | 语音指令执行器（短语 → 电机/舵机/蜂鸣/LED） | sub `/voice/voice_command`；pub `/cmd_vel`、`/servo_controller`、`set_buzzer`、`/voice/status_led` |
| `voice_feedback` | ament_python | 唤醒与识别结果提示音 + 蜂鸣器 + LED 反馈 | pub `set_buzzer`、`/voice/status_led` |
| `voice_msgs` | ament_cmake | 语音自定义消息（`VoiceCommand` 等） | — |

## 视觉 / 融合 / 底盘复用模块

| 目录 | 状态 | 说明 |
|------|------|------|
| `src/vision/depth_processor` | 已实现 | 深度图处理（订阅 `/camera/depth/image_raw`） |
| `src/vision/vision_msgs` | 已实现 | 视觉自定义消息 |
| `src/vision/image_preprocess` | **未实现** | 图像预处理（launch / run_all.sh 中仍被引用） |
| `src/vision/object_detection` | **未实现** | YOLOv8 + ONNX/TensorRT 目标检测（同上） |
| `src/fusion/fusion_node` | 已实现 | 多模态融合节点（订阅 `/voice/voice_command`，发布 `/fusion/result`） |
| `src/fusion/fusion_msgs` | 已实现 | 融合自定义消息 |
| `src/jetauto_app` | 已实现 | 上层应用节点：`servo_tracker`（声源跟随舵机/整车旋转）、`lidar_controller`、`twist_to_motor_bridge` |
| `src/jetauto_peripherals` | 已实现 | 外设：`servo_control`（显式舵机控制）、`teleop_key_control`（键盘控制） |
| `src/navigation`、`src/slam` | 已实现 | 导航（Nav2）与激光 SLAM（SLAM Toolbox）启动/参数/RViz/地图 |
| `src/interfaces`、`src/ros_robot_controller_msgs` | 已实现 | 与 Pi3 共用的消息/服务定义 |
| `src/orbbec_ws` | submodule | Orbbec Astra Pro ROS2 驱动（`ros2_astra_camera`） |

## 项目目录结构

```
HiJetson/
├── README.md
├── CLAUDE.md                      # CC 项目上下文
├── Changelog/                     # 版本日志（当前最新 0.9.9）
├── docs/
│   ├── design.md                  # 详细设计（模块/消息/话题/性能）
│   └── deployment.md              # 部署指南（安装/启动/使用）
├── scripts/
│   ├── setup_jetson.sh            # 一键环境安装
│   ├── setup_respeaker.sh         # ReSpeaker 权限设置
│   ├── 99-respeaker.rules         # ReSpeaker udev 规则（DOA 需要）
│   ├── download_models.sh         # 模型下载（Vosk / Whisper）
│   ├── run_voice.sh               # 只启语音管线
│   ├── run_vision.sh              # 只启视觉管线
│   ├── run_all.sh                 # 全系统启动
│   ├── monitor_topics.sh          # 话题监控
│   ├── respeaker_asr_test.py      # 唤醒词 + ASR 独立测试
│   └── clean.sh                   # 清理
└── src/
    ├── config/                    # voice_params.yaml / vision_params.yaml / system_params.yaml
    ├── launch/                    # hijetson_voice / hijetson_vision / hijetson_all.launch.py
    ├── voice/                     # 语音包组（8 个包，见上表）
    ├── vision/                    # depth_processor / vision_msgs（+2 个未实现包）
    ├── fusion/                    # fusion_node / fusion_msgs
    ├── jetauto_app/               # servo_tracker、lidar_controller、twist_to_motor_bridge
    ├── jetauto_peripherals/       # servo_control、teleop_key_control
    ├── navigation/                # Nav2 导航
    ├── slam/                      # SLAM Toolbox 建图/定位
    ├── interfaces/                # 自定义消息与服务
    ├── ros_robot_controller_msgs/ # 控制板消息（舵机/蜂鸣器/LED）
    └── orbbec_ws/                 # Orbbec Astra Pro 驱动（submodule）
```

> **详细设计**（模块说明/消息结构/话题一览/性能预期）见 [docs/design.md](docs/design.md)
> **部署指南**（环境要求/安装步骤/启动方式/常见问题）见 [docs/deployment.md](docs/deployment.md)

## 话题一览

| Topic | 类型 | 发布者 → 订阅者 | 说明 |
|-------|------|-----------------|------|
| `/voice/audio_raw` | Float32MultiArray | voice_capture → voice_vad | 原始音频帧（16kHz, float32） |
| `/voice/vad_hw` | Bool | voice_doa → voice_vad | XVF3000 硬件 VAD 状态 |
| `/voice/audio_clip` | Float32MultiArray | voice_vad → voice_hotword | 完整语音片段 |
| `/voice/voice_activity` | Bool | voice_vad | 语音活动状态 |
| `/voice/wake` | Bool | voice_hotword → voice_asr、servo_tracker | 唤醒/休眠信号（True=唤醒） |
| `/voice/audio_for_asr` | Float32MultiArray | voice_hotword → voice_asr | 送 Whisper 的音频（ASR 直通模式） |
| `/voice/asr_result` | String | voice_asr → voice_hotword、voice_feedback | Whisper 转写结果 |
| `/voice/voice_command` | VoiceCommand | voice_hotword → voice_executor、fusion_node | 结构化语音指令 |
| `/voice/state` | String | voice_hotword | 状态文本（SLEEPING/WAKE/LISTEN…） |
| `/voice/doa_angle` | Float32 | voice_doa → servo_tracker | 校准后声源角度 |
| `/voice/doa_locked` | Float32 | voice_doa → servo_tracker | VAD 上升沿锁存角度 |
| `/voice/doa_direction` | String | voice_doa | 方向文本 |
| `/voice/status_led` | ColorRGBA | voice_executor、voice_feedback → voice_doa | LED 灯环反馈（亮完恢复 DOA 指示） |
| `/cmd_vel` | Twist | voice_executor、servo_tracker → Pi3 | 底盘速度指令（0.5s 自动停 / 开环旋转） |
| `/servo_controller` | ServosPosition | voice_executor、servo_tracker → Pi3 | 总线舵机脉冲指令（312-688，±45°） |
| `/ros_robot_controller/set_buzzer` | BuzzerState | voice_executor、voice_feedback → Pi3 | 蜂鸣器 |
| `/camera/depth/image_raw` | Image | astra_camera → depth_processor | 深度图 |
| `/vision/distance_result` | — | depth_processor | 距离测量结果 |
| `/fusion/result` | FusedResult | fusion_node | 多模态融合结果 |

## 快速启动

```bash
# 0. 克隆（含子模块）
git clone --recurse-submodules http://192.168.3.96:3000/legend/HiJetson.git
cd HiJetson

# 1. 编译
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
export ROS_DOMAIN_ID=42          # 与 Pi3 一致

# 2. 启动语音管线（含唤醒词、DOA、指令执行）
ros2 launch src/launch/hijetson_voice.launch.py
# 或：bash scripts/run_voice.sh
```

说 **小车小车**（Vosk 短语模式）或 **小方小方**（ASR 直通）唤醒，**退出** 休眠。

```bash
# 查看识别结果
ros2 topic echo /voice/asr_result
# 查看唤醒状态
ros2 topic echo /voice/state
# 查看节点/话题
ros2 node list && ros2 topic list
```

参数集中在 `src/config/voice_params.yaml`（采集 / VAD / 热词 / ASR / DOA / servo_tracker）。

## 已知问题

- `src/launch/hijetson_all.launch.py` 与 `scripts/run_all.sh` 仍引用未实现的 `image_preprocess`、`object_detection` 包，直接运行会报找不到可执行文件
- `/voice/state`（hotword 发布）、`/voice/voice_activity`（voice_vad 发布）目前无订阅方：前者是调试用状态文本，后者是能量 VAD 时代 ASR 门控的遗留，暂留着可 ros2 topic echo 观察

## 路线图

- [x] 项目初始化 + Orbbec Astra Pro 驱动集成
- [x] 软件架构设计 + 文档体系
- [x] ROS2 包框架 / 配置文件体系 / launch 文件
- [x] 部署、启动、监控脚本
- [x] 语音采集节点 (voice_capture)
- [x] VAD 节点 (voice_vad，XVF3000 硬件 VAD)
- [x] 声源定位节点 (voice_doa，pyusb + 镜像校准)
- [x] 唤醒词节点 (voice_hotword，Vosk 双唤醒)
- [x] ASR 节点 (voice_asr，openai-whisper CUDA)
- [x] 指令执行节点 (voice_executor) + 提示反馈 (voice_feedback)
- [x] 声源跟随舵机/整车旋转 (jetauto_app/servo_tracker)
- [x] 深度处理节点 (depth_processor)
- [ ] 图像预处理节点 (image_preprocess)
- [ ] YOLOv8 + ONNX/TensorRT 检测节点 (object_detection)
- [ ] 多模态融合节点完善 (fusion_node)
- [ ] Jetson 实机部署测试 + 性能调优

## 参考资料

- [Orbbec Astra Camera ROS2 Driver](https://github.com/orbbec/ros2_astra_camera)
- [NVIDIA Jetson Orin Nano 官方文档](https://developer.nvidia.com/embedded/learn/jetson)
- [NVIDIA TensorRT 10.7 文档](https://docs.nvidia.com/deeplearning/tensorrt/)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [Vosk 语音识别工具包](https://alphacephei.com/vosk/)
- [ReSpeaker Mic Array v2.0](https://wiki.seeedstudio.com/ReSpeaker_Mic_Array_v2.0/)

## 许可证

本项目基于 Apache License 2.0 开源协议。
