# HiJetson — Jetson Orin Nano × Orbbec Astra Pro 多模态感知系统

## 项目简介
基于 NVIDIA Jetson Orin Nano 8GB 平台，配合 Orbbec Astra Pro 深度相机的多模态感知系统。集成语音采集/识别与图像采集/识别两个核心模块。

## 硬件平台
- **核心计算**: NVIDIA Jetson Orin Nano 8GB (JetPack R36.5.0, Ubuntu 22.04)
- **深度相机**: Orbbec Astra Pro (RGB 1080P + Depth 640×480)
- **底层**: CUDA 12.6 + TensorRT 10.7 + ROS2 Humble

## 项目结构
```
HiJetson/
├── docs/
│   ├── design.md            # 详细设计文档
│   └── deployment.md        # 部署指南
├── src/
│   ├── voice/               # 语音模块包组 (ROS2 Python)
│   │   ├── voice_capture/   # 音频采集节点 (sounddevice)
│   │   ├── voice_vad/       # 语音活动检测节点 (WebRTC VAD)
│   │   ├── voice_wake_word/ # 唤醒词检测节点 (OpenWakeWord)
│   │   ├── voice_asr/       # 语音识别节点 (openai-whisper GPU)
│   │   └── voice_msgs/      # 语音自定义消息
│   ├── vision/              # 视觉模块包组 (ROS2 Python)
│   │   ├── image_preprocess/ # 图像预处理节点
│   │   ├── object_detection/ # 目标检测节点 (YOLO + TensorRT)
│   │   ├── depth_processor/  # 深度处理节点
│   │   └── vision_msgs/      # 视觉自定义消息
│   ├── fusion/              # 多模态融合
│   │   ├── fusion_node/     # 融合节点
│   │   └── fusion_msgs/     # 融合自定义消息
│   ├── models/yolo/         # YOLO ONNX 模型
│   ├── config/              # YAML 配置文件
│   └── launch/              # ROS2 launch 文件
├── scripts/                 # 部署脚本
│   ├── setup_jetson.sh      # 一键安装
│   ├── run_voice.sh         # 启动语音
│   ├── run_vision.sh        # 启动视觉
│   └── clean.sh             # 清理
└── CLAUDE.md                # 本文件
```

## 语音流水线
```
capture → /voice/audio_raw
              ├→ VAD → /voice/audio_clip ──→ ASR (gated)
              └→ wake_word → /voice/wake_word ──→ ASR (wake gate)
```

## 编码规范
- **语言**: Python 3.10 (ROS2 Python nodes), C++ (astra_camera driver)
- **ROS2 包**: Python 包用 setup.py/setup.cfg, C++ 包用 CMakeLists.txt
- **Python 代码风格**: PEP 8, 4空格缩进
- **文档**: Google style docstrings
- **YAML 配置**: 2空格缩进

## 构建与运行
```bash
# 编译前必须 source ROS2 环境
source /opt/ros/humble/setup.bash

cd /workspace/HiJetson
colcon \
  --log-base /root/build/HiJetson/log \
  build \
  --symlink-install \
  --build-base /root/build/HiJetson/build \
  --install-base /root/build/HiJetson/install \
  --cmake-args "-DCMAKE_C_COMPILER=/usr/bin/gcc" "-DCMAKE_CXX_COMPILER=/usr/bin/g++"
# 注: --cmake-args 是因为 /usr/local/bin/cc (Claude Code) 占用了 cc 命令名
#     导致 CMake 找到的是 cc 脚本而非真正的 gcc，必须显式指定编译器
```

## 部署到目标设备 (Jetson Orin Nano)
```bash
# 编译完成后 SCP 到 Jetson
scp -r /root/build/HiJetson/install nvidia@<jetson-ip>:/home/nvidia/HiJetson/

# (如首次) 还需同步 scripts/ config/ launch/ 等源文件
rsync -av /workspace/HiJetson/{scripts,src/config,src/launch} nvidia@<jetson-ip>:/workspace/HiJetson/
```

## 在 Jetson 上运行
```bash
cd /home/nvidia/HiJetson
source install/setup.bash

# 启动语音管线（带唤醒词）
bash scripts/run_voice.sh

# 启动视觉管线
bash scripts/run_vision.sh

# 查看 ASR 结果
ros2 topic echo /voice/asr_result
```

## 关键配置
- 语音参数: `src/config/voice_params.yaml`
- 视觉参数: `src/config/vision_params.yaml`
- 系统参数: `src/config/system_params.yaml`
- 唤醒词: "Hey Jarvis" (OpenWakeWord)
- 需要先停止 PulseAudio: `systemctl --user stop pulseaudio.service pulseaudio.socket`

## 音频注意事项
- ASTRA Pro 为 2 通道 USB 音频设备, ALSA card 0
- PulseAudio 会冲突, 启动前必须暂停
- Whisper 使用 CUDA GPU, 脉冲占用 ~1.5GB
- YOLO 使用 TensorRT, 常驻 ~400MB GPU 内存

## 未完成项（待开发）
- [ ] image_preprocess 节点
- [ ] object_detection 节点 (YOLOv8 + ONNX/TensorRT)
- [ ] depth_processor 节点
- [ ] fusion_node 多模态融合

## 每日收尾流程
每天工作结束时执行：
```bash
# 1. 查看当天 git 变更
cd /workspace/HiJetson
git diff --stat

# 2. 确定新版本号 (当前最大版本 + 0.0.1)
#    查看当前版本: ls Changelog/ | sort -V | tail -1
#    创建新文件: Changelog/0.9.4.md (格式参考已有文件)

# 3. 更新 Changelog/0.x.x.md
#    格式: "# 版本号 (YYYY-MM-DD)" → 项目状态 → 已完成(模块分类) → 待完成 → 已知问题 → 技术债务

# 4. 提交推送
git add -A
git commit -m "chore: release 0.9.4"
git push
```
