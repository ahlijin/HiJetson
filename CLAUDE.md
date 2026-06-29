# HiJetson — Jetson Orin Nano 机器人感知与控制

基于 NVIDIA Jetson Orin Nano 8GB 平台，配合 Orbbec Astra Pro 深度相机的机器人端工作空间。
集成视觉感知、语音交互、SLAM 建图和自主导航。

## 分支说明
- **main**: 开发分支，包含语音/视觉/SLAM/导航全套代码
- **lite**: 存档分支，仅包含从 HiWonder_JetAuto 迁移的已验证 SLAM/导航代码（只读）

## 硬件平台
- **核心计算**: NVIDIA Jetson Orin Nano 8GB (JetPack R36.5.0, Ubuntu 22.04)
- **深度相机**: Orbbec Astra Pro (RGB 1080P + Depth 640×480)
- **底层**: CUDA 12.6 + TensorRT 10.7 + ROS2 Humble
- **通信**: ROS_DOMAIN_ID=42, 与 Pi3 协同

## 项目结构
```
HiJetson/
├── src/
│   ├── voice/               # 语音模块 (capture → VAD → wake_word → ASR)
│   ├── vision/              # 视觉模块 (depth_processor + 待补 object_detection)
│   ├── fusion/              # 多模态融合节点
│   ├── slam/                # SLAM (slam_toolbox + rtabmap)
│   ├── navigation/          # Nav2 自主导航
│   ├── jetauto_peripherals/ # 舵机控制、键盘遥控、深度相机启动
│   ├── interfaces/          # 坐标/位姿消息定义
│   ├── ros_robot_controller_msgs/ # 控制板消息 (与 Pi3 共享)
│   ├── config/              # 配置文件
│   ├── launch/              # 启动文件
│   └── orbbec_ws/           # Orbbec Astra Pro 驱动 (submodule)
├── scripts/                 # 部署与运行脚本
└── docs/                    # 设计文档
```

## 构建
```bash
source /opt/ros/humble/setup.bash
cd <workspace>
colcon \
  --log-base /root/build/HiJetson/log \
  build \
  --symlink-install \
  --build-base /root/build/HiJetson/build \
  --install-base /root/build/HiJetson/install \
  --cmake-args "-DCMAKE_C_COMPILER=/usr/bin/gcc" "-DCMAKE_CXX_COMPILER=/usr/bin/g++"
```

## 开发重点
1. 视觉跟随 (YOLO + depth → cmd_vel)
2. 障碍物规避 (depth + LiDAR)
3. 语音交互 (见 voice/ 模块)
4. SLAM 建图与导航 (slam/ + navigation/)
