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

## 一键安装（Jetson Orin Nano）

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

## 手动部署步骤

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

# 4. 启动系统
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
# 或
ros2 launch src/launch/hijetson_voice.launch.py
```

### 仅启动视觉模块（测试目标检测）

```bash
./scripts/run_vision.sh
# 或
ros2 launch src/launch/hijetson_vision.launch.py
```

### 系统监控

```bash
# 查看所有活跃话题
ros2 topic list

# 查看语音命令
ros2 topic echo /voice/voice_command

# 查看检测结果
ros2 topic echo /vision/detection_result

# 查看融合结果
ros2 topic echo /fusion/result
```

### 停止系统

按 `Ctrl+C` 即可优雅停止所有节点。

## 清理

```bash
# 清理编译产物
rm -rf build/ install/ log/

# 或使用清理脚本
./scripts/clean.sh