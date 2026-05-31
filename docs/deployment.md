# 部署指南

## 前提条件

| 软件 | 版本 | 说明 |
|------|------|------|
| JetPack | **R36.5.0** (L4T 36.5.0) | 已安装在 Jetson |
| ROS2 | **Humble** | `/opt/ros/humble` |
| CUDA | **12.6.11** | `/usr/local/cuda-12.6` |
| TensorRT | **10.7.0.23** | 已安装 |
| Python | **3.10.12** | 已安装 |
| PyTorch | **2.5.0a0+nv24.08** | JetPack 优化版 |
| OpenCV | **4.10.0** | 已安装 |

## 首次部署（Jetson Orin Nano）

```bash
# 1. 克隆项目及子模块
git clone https://github.com/ahlijin/HiJetson.git
cd HiJetson
git submodule update --init --recursive

# 2. 一键安装
sudo chmod +x scripts/setup_jetson.sh
./scripts/setup_jetson.sh

# 3. 设置 USB 设备权限
cd src/orbbec_ws/astra_camera/scripts
sudo bash install.sh
sudo udevadm control --reload-rules && sudo udevadm trigger
cd ../../..

# 4. 安装 openai-whisper（语音识别，PyTorch CUDA）
pip3 install openai-whisper

# 注意: openai-whisper 依赖 numba，而 numba 与高版本 coverage 不兼容。
# 如果遇到 "AttributeError: module 'coverage' has no attribute 'types'" 错误，
# 降级 coverage:
pip3 install "coverage==6.5.0"

# 5. 编译工作空间
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 启动语音模块

### 重要：ASTRA Pro 麦克风与 PulseAudio 冲突

Jetson 上 PulseAudio 默认占用 USB 音频设备（ASTRA Pro），导致 sounddevice 无法通过 ALSA 直通访问。必须在启动前临时停止 PulseAudio：

```bash
# 停止 PulseAudio（不抑制，只是临时挂起）
systemctl --user stop pulseaudio.service pulseaudio.socket
```

> 如果后续使用需要 PulseAudio（如 HDMI 音频输出），重启即可恢复：
> ```bash
> systemctl --user start pulseaudio.service
> ```

### 启动方式

```bash
cd HiJetson
source install/setup.bash

# 方式一：launch 文件（推荐）
ros2 launch src/launch/hijetson_voice.launch.py

# 方式二：启动脚本
./scripts/run_voice.sh
```

### 查看结果

另一个终端：

```bash
cd HiJetson
source install/setup.bash

# 查看 ASR 识别结果
ros2 topic echo /voice/asr_result

# 查看语音活动状态
ros2 topic echo /voice/voice_activity

# 查看所有活跃话题
ros2 topic list
```

### 麦克风设备配置

ASTRA Pro 通过 ALSA 直通（需停止 PulseAudio）：
- 设备索引: 0
- 采样率: 16kHz
- 通道: 2（立体声，代码内自动混音为单声道）
- 帧长: 1600 样本（100ms）

如使用 PulseAudio 默认设备，将 `device_index` 改为 `-1`。

## VAD 参数调优

WebRTC VAD 有 4 个敏感度级别（0-3）：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| 0 | 最宽松 | 安静环境 |
| 1 | 适中 | 一般室内（默认） |
| 2 | 较严格 | 有风扇/空调噪声 |
| 3 | 最严格 | 嘈杂环境 |

修改 `src/launch/hijetson_voice.launch.py` 中的 `vad_mode` 参数。

## ASR 模型配置

当前使用 **openai-whisper** 的 `tiny` 模型，在 Jetson Orin Nano GPU 上推理速度约 0.3s/片段。

支持模型切换（在 `hijetson_voice.launch.py` 中修改 `model_size`）：

| 模型 | 大小 | GPU 推理速度 | 准确率 |
|------|------|-------------|--------|
| tiny | ~75MB | ~0.3s | 基础 |
| base | ~140MB | ~0.5s | 较好 |
| small | ~460MB | ~1.5s | 良好 |

> 模型首次使用时自动下载并缓存到 `~/.cache/whisper/`。

## 停止系统

按 `Ctrl+C` 即可优雅停止所有节点。

## 常见问题

### "Failed to start audio stream: Invalid number of channels"

**原因：** PulseAudio 正在运行，占用了 ASTRA Pro 设备，或设备索引号不对。

**解决：**
```bash
systemctl --user stop pulseaudio.service pulseaudio.socket
# 确认 ASTRA Pro 在设备 0
python3 -c "import sounddevice as sd; [print(f'[{i}] {d[\"name\"]}') for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]"
```

### 启动后 VAD 一直显示说话，但 ASR 无结果

**原因：** 环境噪声被 VAD 当作语音触发，但 whisper 检测不到实际语音内容。

**解决：** 提高 VAD 敏感度（`vad_mode: 3`）或靠近麦克风清晰说话。

### AttributeError: module 'coverage' has no attribute 'types'

**原因：** numba 与高版本 coverage 不兼容。

**解决：**
```bash
pip3 install "coverage==6.5.0"
```

### ros2 run 报 "No executable found"

**原因：** ament_python 包的 console_scripts 默认装到 `bin/`，但 `ros2 run` 只在 `lib/<包名>/` 查找。

**解决：** 项目已在各语音包的 `setup.cfg` 中配置了 `script_dir`，重新编译即可：
```bash
colcon build --symlink-install --packages-select voice_capture voice_vad voice_asr
```

## 清理

```bash
# 清理编译产物
rm -rf build/ install/ log/

# 或使用清理脚本
./scripts/clean.sh
```
