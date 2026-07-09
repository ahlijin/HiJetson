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
pip3 install sounddevice numpy scipy openai-whisper opencc-python-reimplemented

# 3. 编译
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 语音管线架构

```
ReSpeaker (ALSA直连)
  → voice_capture (16kHz, 无增益)
    → /voice/audio_raw
      → voice_vad (能量VAD, 阈值0.02)
        → /voice/audio_clip
          → voice_asr (Whisper base)
            → 检测"小车小车"/"小红小红"/"小绿小绿"/"小方小方"? → 唤醒
            → 唤醒后解析指令: 左转/右转/蜂鸣
            → opencc 繁转简 → /voice/asr_result
```

## 启动

```bash
source install/setup.bash
export ROS_DOMAIN_ID=42

# 逐个启动
voice_capture_node &
voice_vad_node &
voice_asr_node &
ros2 run voice_feedback voice_feedback_node &

# 查看结果
ros2 topic echo /voice/asr_result
```

## 唤醒词

| 唤醒词 | 说明 |
|--------|------|
| 小车小车 | 标准唤醒 |
| 小红小红 | 备用唤醒 |
| 小绿小绿 | 备用唤醒 |
| 小方小方 | 备用唤醒 |

## 语音指令（唤醒后8秒内）

| 指令 | 动作 |
|------|------|
| 左转 / 左拐 | 舵机左转 |
| 右转 / 右拐 | 舵机右转 |
| 蜂鸣 / 响 | 蜂鸣器响 |

## 独立测试脚本（不依赖 ROS2）

```bash
python3 scripts/respeaker_asr_continuous.py
```

能量 VAD → Whisper → opencc，直接说话自动识别，无唤醒词。

## 常见问题

### ReSpeaker 在 ALSA 中不显示

Jetson 偶发 `snd-usb-audio` 未加载：

```bash
sudo modprobe snd-usb-audio
echo 'snd-usb-audio' | sudo tee -a /etc/modules  # 开机自启
```

### 识别结果乱码/胡言乱语

ReSpeaker USB 连接不稳定会导致音频质量差，拔插 USB 线或重启 Jetson 即可恢复。

### asr_result 无输出

检查各节点运行状态和各 topic 发布情况：

```bash
ros2 node list | grep voice
ros2 topic info /voice/audio_raw -v
ros2 topic info /voice/audio_clip -v
```
