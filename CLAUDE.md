# HiJetson — Jetson Orin Nano 机器人感知与控制

基于 NVIDIA Jetson Orin Nano 8GB 平台，配合 Orbbec Astra Pro 深度相机 + ReSpeaker Mic Array v2.0 的机器人端工作空间。
集成视觉感知、语音交互、SLAM 建图和自主导航。

## 分支说明
- **main**: 开发分支，包含语音/视觉/SLAM/导航全套代码
- **lite**: 存档分支，仅包含从 HiWonder_JetAuto 迁移的已验证 SLAM/导航代码（只读）

## 仓库
- origin: http://192.168.3.96:3000/legend/HiJetson.git （本地 gitea，NAS 与 github 在线仓库已弃用）
- 子模块 `src/orbbec_ws` = legend/ros2_astra_camera（gitea）；`git clone --recurse-submodules` 拉取
- 姊妹仓库: legend/HiWonder_JetAuto（Pi3 底层控制）

## 硬件平台
- **核心计算**: NVIDIA Jetson Orin Nano 8GB (JetPack R36.5.0, Ubuntu 22.04)
- **深度相机**: Orbbec Astra Pro (RGB 1080P + Depth 640×480)
- **麦克风阵列**: ReSpeaker Mic Array v2.0 (XVF3000, USB Audio + HID DOA, 板载波束成形+降噪)
- **底层**: CUDA 12.6 + TensorRT 10.7 + ROS2 Humble
- **通信**: ROS_DOMAIN_ID=42, 与 Pi3 协同

## 项目结构
```
HiJetson/
├── src/
│   ├── voice/               # 语音模块 (8 包: capture/doa/vad/hotword/asr/executor/feedback/msgs)
│   ├── vision/              # 视觉模块 (depth_processor + vision_msgs; image_preprocess/object_detection 待实现)
│   ├── fusion/              # 多模态融合节点
│   ├── jetauto_app/         # servo_tracker 声源跟随 / lidar_controller / twist_to_motor_bridge
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

### 开发机：宿主 Pi5 的 my-ros docker 容器（实测可用）
```bash
docker run --rm \
  -v /home/pi/hermes-data/code/HiJetson:/ws \
  -v /home/pi/hermes-data/build/HiJetson:/out \
  my-ros:latest bash -lc '
    source /opt/ros/humble/setup.bash && cd /ws &&
    colcon --log-base /out/log build --build-base /out/build --install-base /out/install \
      --cmake-args -DCMAKE_C_COMPILER=/usr/bin/gcc -DCMAKE_CXX_COMPILER=/usr/bin/g++'
# 镜像 my-ros:latest = ROS2 Humble + colcon (aarch64, Python 3.10)
# 挂载必须传宿主机路径: Hermes 容器内 /opt/data == 宿主机 /home/pi/hermes-data
# 只编指定包加 --packages-select <pkg>（astra_camera 是 C++ 大包，非必要别全编）
# 产物落在 /out(=宿主机 /home/pi/hermes-data/build/HiJetson)，源码只读挂载更安全
```

### Jetson 上原生编译（部署用）
```bash
source /opt/ros/humble/setup.bash
cd ~/HiJetson
colcon build --symlink-install \
  --cmake-args "-DCMAKE_C_COMPILER=/usr/bin/gcc" "-DCMAKE_CXX_COMPILER=/usr/bin/g++"
# 注: /usr/local/bin/cc 被 Claude Code 占用时必须显式指定 gcc/g++；
#     若产物要 scp 到别处，不要用 --symlink-install（symlink 指本机路径，scp 后失效）
```

## 开发重点
1. 视觉跟随 (YOLO + depth → cmd_vel)
2. 障碍物规避 (depth + LiDAR)
3. 语音交互 (见 voice/ 模块)
4. SLAM 建图与导航 (slam/ + navigation/)
