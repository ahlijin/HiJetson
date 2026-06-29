# HiJetson Lite — 机器人 Jetson Orin Nano 运行分支

已验证的 Jetson 侧完整工作空间，包含 SLAM、导航、深度相机、舵机控制和键盘遥控。

## 来源
从 HiWonder_JetAuto `jetson/` 移植的已验证代码，作为独立分支管理。

## 项目结构
```
HiJetson/
├── src/
│   ├── interfaces/              # 自定义消息 (Point2D, Pose2D 等)
│   ├── jetauto_peripherals/     # 舵机控制、键盘遥控、深度相机启动
│   ├── navigation/              # Nav2 导航配置、RTAB-Map
│   ├── ros_robot_controller_msgs/ # 控制板消息 (复用于 Pi3 通信)
│   ├── slam/                    # SLAM Toolbox 建图 + rtabmap
│   └── orbbec_ws/               # Orbbec Astra Pro 深度相机驱动 (submodule)
├── *.sh                         # 启动脚本
└── CLAUDE.md
```

## 构建
```bash
source /opt/ros/humble/setup.bash
cd <workspace>
colcon build --symlink-install
```

## 部署到 Jetson Orin Nano
```bash
# 编译后 scp 到 Jetson
scp -r install nvidia@<jetson-ip>:/home/nvidia/jetson_ws/
```

## 启动方式
```bash
cd ~/jetson_ws && source install/setup.bash && export ROS_DOMAIN_ID=42

# 启动 SLAM 建图（ssh友好）
./jetson_start.sh

# 键盘控制
./jetson_teleop.sh

# 桌面版 SLAM（含 RViz）
./jetson_slam.sh

# 导航
./jetson_navigation.sh
```

## 与 main 分支关系
- **main**: 语音 + 视觉 + 融合流水线开发
- **lite** (本分支): 已验证的 SLAM/导航/控制
- 开发完成后合并为完整机器人代码
