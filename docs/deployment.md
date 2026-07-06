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

### 麦克风：ReSpeaker Mic Array v2.0 (XVF3000)

基于 XVF3000 的 USB 麦克风阵列，输出经板载波束成形和降噪处理的干净音频：
- 接口：USB Audio Class 1.0
- 输出：左声道 beamformed mono, 右声道 AEC 参考 (无播放时忽略)
- 采样率：48kHz native (capture 节点内部重采样到 16kHz)
- 板载处理：波束成形 + 自适应降噪 + 去混响 + 声源定位 (DOA)
- 无需停止 PulseAudio，走默认输入设备即可

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

### 麦克风设备确认

首次使用或遇到音频问题时，先确认 ReSpeaker 被正确识别：

```bash
# 列出所有音频输入设备
python3 -c "import sounddevice as sd; [print(f'[{i}] {d[\"name\"]} (ch={d[\"max_input_channels\"]})') for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]"

# 预期输出示例（Astra Pro 深度相机仍会出现在列表中，但已不使用其音频）：
# [2] ReSpeaker 4 Mic Array (XFW3000): USB Audio, ch=2
```

> **注意：** Astra Pro 深度相机的 USB 音频接口（`ASTRA Pro` 设备）仍会出现在设备列表里，但 capture 节点通过 PulseAudio 默认输入自动选择 ReSpeaker。如需确认当前默认输入，运行：
> ```bash
> pactl info | grep 'Default Source'
> ```

### XVF3000 板载处理说明

与之前 Astra Pro 内置麦克风方案的关键差异：

| 方面 | Astra Pro 内置麦克风 (旧) | ReSpeaker v2.0 XVF3000 (新) |
|------|--------------------------|------------------------------|
| 通道 | 2ch → 软件混音单声道 | 1ch beamformed (XVF3000 硬件输出) |
| 降噪 | 软件 HPF 300Hz (有源) | 板载自适应降噪（无需软件滤波） |
| 波束成形 | 无 | 板载多麦克风波束成形 |
| PulseAudio | 曾有冲突需停止 | 走默认输入，无冲突 |
| 风扇噪声 | 严重，需 HPF 处理 | 板载滤波已抑制 |
| 声源定位 | 无 | XVF3000 HID DOA (30° 分辨率) |

## DOA 声源定位

### 原理

XVF3000 芯片通过 6 麦克风环形阵列进行波束成形，实时计算声源方向（DOA, Direction of Arrival），并通过 USB HID 接口输出。

- 角度分辨率: 30° (12 个扇区: 0-11)
- 方向标签: front / front_right / right / right_back / back / left_back / left / left_front
- 无方向时: `none` (角度值 -1.0)
- 轮询频率: 10Hz (默认，可在 `voice_params.yaml` 中调整)

### 启动

DOA 节点随语音模块一起启动：

```bash
# 语音模块（包含 DOA）
ros2 launch src/launch/hijetson_voice.launch.py

# 或单独启动 DOA 节点
ros2 run voice_doa voice_doa_node
```

### 查看 DOA 数据

```bash
# 实时角度 (度)
ros2 topic echo /voice/doa_angle

# 方向标签
ros2 topic echo /voice/doa_direction
```

### 声源跟踪（舵机云台）

调用 `servo_tracker` 节点将 DOA 角度转换为舵机脉冲，驱动云台转向声源：

```bash
# 随完整系统启动（已集成在 hijetson_all.launch.py）
ros2 launch src/launch/hijetson_all.launch.py

# 或单独启动
ros2 run jetauto_app servo_tracker
```

**舵机映射：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `servo_pan_id` | 1 | 水平舵机 ID |
| `center_pulse` | 1500 | 正前方脉冲值 (μs) |
| `range_pulse` | 1000 | 最大偏移 (±1000 = 500~2500) |
| `angle_range` | 180.0 | 映射范围 (±90°) |
| `center_timeout` | 2.0 | 无 DOA 时自动回中 (秒) |

> 如果 ReSpeaker 安装有偏（如非正对前方），在 `voice_params.yaml` 中设置 `voice_doa.angle_offset` 校准。

### 依赖安装

DOA 功能需要以下 Python 包，在 Jetson 上安装：

```bash
# pyusb — USB vendor control transfer (首选 DOA 后端)
pip3 install pyusb

# hidapi — HID 回退后端
sudo apt install libhidapi-libusb0
pip3 install hidapi

# pixel-ring — LED 灯环控制
pip3 install pixel-ring
```

后端自动检测顺序：`pyusb` → `hidapi` → `hidraw`。如需强制指定，在 `voice_params.yaml` 中设 `voice_doa.backend`。

### 设备权限（udev 规则）

默认情况下非 root 用户无法读取 `/dev/hidraw*` 上的 HID 报告。项目提供了 udev 规则：

```bash
# 安装 udev 规则
sudo cp scripts/99-respeaker.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# 确认权限生效
ls -l /dev/hidraw*  # 应显示 crw-rw-rw-
```

规则文件路径：`scripts/99-respeaker.rules`，匹配 VID:PID `2886:0018`（Seeed）和 `20b1:0005`（XMOS）。

### 设备确认

```bash
# 查看 XVF3000 HID 设备
lsusb | grep -i -E "xvf|respeaker|seeed"
# 预期输出: 2886:0018 Seeed Technology Co., Ltd.
python3 -c "
import hid
for d in hid.enumerate():
    if d['vendor_id'] == 0x2886 or d['product_id'] == 0x0018:
        print(f'HID: VID=0x{d[\"vendor_id\"]:04x} PID=0x{d[\"product_id\"]:04x} {d[\"product_string\"]}')
"
```

### LED 灯环

ReSpeaker v2.0 板载 12 颗 LED 灯环，默认在 DOA trace 模式下随声源方向自动亮灯。

通过话题控制颜色：

```bash
# 设置红色 3 秒后自动恢复 trace 模式
ros2 topic pub /voice/status_led std_msgs/ColorRGBA "{r: 1.0, g: 0.0, b: 0.0, a: 1.0}" --once
```

> 需要安装 `pip3 install pixel-ring`，且 DOA 使用 pyusb 后端。

### XVF3000 参数调优

通过 service 实时读写任意寄存器：

```bash
# 读取当前 HPF 状态
ros2 service call /voice/respeaker_get_param example_interfaces/srv/SetString "{data: 'HPFONOFF'}"

# 设置 HPF 到 125Hz 截止
ros2 service call /voice/respeaker_set_param example_interfaces/srv/SetString "{data: 'HPFONOFF=2'}"

# 关闭 AGC（自动增益控制）
ros2 service call /voice/respeaker_set_param example_interfaces/srv/SetString "{data: 'AGCONOFF=0'}"

# 设置 VAD 门限
ros2 service call /voice/respeaker_set_param example_interfaces/srv/SetString "{data: 'GAMMAVAD_SR=3.5'}"
```

可用参数列表：`HPFONOFF`, `AGCONOFF`, `AGCMAXGAIN`, `AGCDESIREDLEVEL`, `STATNOISEONOFF`, `NONSTATNOISEONOFF`, `ECHOONOFF`, `FREEZEONOFF`, `GAMMAVAD_SR`, `AECFREEZEONOFF` 等。

## VAD 参数调优

VAD 使用 XVF3000 芯片内置的语音活动检测，通过寄存器读取，CPU 零开销。无可调参数。

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

### VoiceCaptureNode 启动后无音频数据

**原因：** PulseAudio 默认输入设备不是 ReSpeaker，或 ReSpeaker 未被识别。

**解决：**
```bash
# 确认 ReSpeaker 出现在输入设备列表中
python3 -c "import sounddevice as sd; [print(f'[{i}] {d[\"name\"]}') for i,d in enumerate(sd.query_devices()) if d['max_input_channels']>0]"

# 如果未出现，检查 USB 连接
lsusb | grep -i xvf

# 确认 PulseAudio 默认输入指向 ReSpeaker
pactl info | grep 'Default Source'
pactl list sources short
```

### 启动后 VAD 一直显示说话，但 ASR 无结果

**原因：** 环境噪声被 VAD 当作语音触发，但 whisper 检测不到实际语音内容。

**解决：** 检查 XVF3000 硬件 VAD 是否工作（见 DOA 章节）或靠近麦克风清晰说话。

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
