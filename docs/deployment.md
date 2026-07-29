# 部署指南

## 前提条件

| 软件 | 版本 | 说明 |
|------|------|------|
| JetPack | **R36.5.0** (L4T 36.5.0) | 已安装在 Jetson |
| ROS2 | **Humble** | `/opt/ros/humble` |
| CUDA | **12.6.11** | `/usr/local/cuda-12.6` |
| Python | **3.10.12** | 已安装 |

## 首次部署（Jetson Orin Nano）

```bash
# 1. 克隆项目
git clone https://github.com/ahlijin/HiJetson.git
cd HiJetson

# 2. 安装依赖
pip3 install sounddevice numpy scipy openai-whisper opencc-python-reimplemented vosk

# 3. 下载 Vosk 中文模型
wget https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
unzip vosk-model-small-cn-0.22.zip -d ~/

# 4. USB 权限（DOA 需要 pyusb 访问 ReSpeaker）
sudo cp scripts/99-respeaker.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
# 重新插拔 ReSpeaker USB

# 5. 编译（注意：astra_camera_msgs 是嵌套包，需 --paths 指定）
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-select astra_camera_msgs --paths src/orbbec_ws/astra_camera_msgs
colcon build --symlink-install

# 5. 环境
source install/setup.bash
export ROS_DOMAIN_ID=<Pi3同一值>
```

## 语音管线架构

```
ReSpeaker (ALSA直连)
  → voice_capture (16kHz)
    → /voice/audio_raw
      → voice_vad (能量VAD, 前缀缓冲)
        → /voice/audio_clip
          → voice_hotword (双唤醒词 + Vosk语法匹配)
              ├── 小车小车 → Vosk 模式 (19短语, CPU)
              └── 小方小方 → ASR 直通 (→ Whisper GPU)

声源定位 & 舵机跟随:
  XVF3000 DOA (pyusb, 不踢ALSA)
    → /voice/doa_angle
      → servo_tracker (语音指令触发)
          ├── 舵机转向声源 (/servo_controller)
          └── 超范围 → cmd_vel 转动小车 (/cmd_vel)

指令执行:
  voice_hotword → /voice/voice_command
    → voice_executor
        ├── 电机: Twist → /cmd_vel (0.5s自动停)
        ├── 舵机: ServosPosition → /servo_controller
        ├── 蜂鸣: BuzzerState → /ros_robot_controller/set_buzzer
        └── LED: ColorRGBA → /voice/status_led
```

## 启动

```bash
source install/setup.bash
export ROS_DOMAIN_ID=<Pi3同一值>

# 一键启动
ros2 launch src/launch/hijetson_voice.launch.py

# 查看节点
ros2 node list
ros2 topic list
```

## 使用

- **小车小车** — 唤醒，Vosk 语法模式，说预设短语直接响应
- **小方小方** — 唤醒，ASR 直通模式，说任意内容 Whisper 转录
- **退出** — 回到休眠状态
