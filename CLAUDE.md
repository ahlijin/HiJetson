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
- **核心计算**: NVIDIA Jetson Orin Nano 8GB（宿主已升级到 JetPack 7 / Ubuntu 24.04；ROS2 Humble 跑在 docker 容器里，见 `scripts/Dockerfile.my-ros`）
- **深度相机**: Orbbec Astra Pro (RGB 1080P + Depth 640×480)
- **麦克风阵列**: ReSpeaker Mic Array v2.0 (XVF3000, USB Audio + HID DOA, 板载波束成形+降噪)
- **底层**: 容器内 Ubuntu 22.04 + ROS2 Humble（宿主 CUDA/TensorRT 通过 `--runtime nvidia` 供容器用）
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
│   ├── hijetson_bringup/    # 启动包: launch 文件 + config/*.yaml (2026-10 起，原来是裸的 src/launch + src/config)
│   └── orbbec_ws/           # Orbbec Astra Pro 驱动 (submodule)
├── scripts/                 # 部署与运行脚本 (start.sh 是容器主进程; Dockerfile.my-ros / docker-compose.yml 也在这)
└── docs/                    # 设计文档
```

## 运行（容器方式，2026-10 起）
```bash
# 设备上（Jetson）：CI 推送 main 自动部署 install/ + start.sh 到 /opt/hijetson，再由容器跑起来
cd /home/nvidia/hijetson
docker compose pull && docker compose up -d --force-recreate   # 拉起/更新
docker compose logs -f                                        # 看管线日志
# 启动哪个管线改 /opt/hijetson/start.sh 顶部 LAUNCH= 一行（compose 不掺业务）
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

### Jetson 上原生编译（已废弃：宿主升级到 Ubuntu 24.04 后装不了 Humble）
```bash
# 老流程（JetPack 6 / Ubuntu 22.04 时）：
source /opt/ros/humble/setup.bash
cd ~/HiJetson
colcon build --symlink-install \
  --cmake-args "-DCMAKE_C_COMPILER=/usr/bin/gcc" "-DCMAKE_CXX_COMPILER=/usr/bin/g++"
# 现在请用容器：scripts/Dockerfile.my-ros 提供镜像，CI 推送自动编译+部署
# 手工编译可用上面的"开发机 my-ros 容器"方式，或直接在设备上：
#   docker run --rm -v $PWD:/ws -w /ws my-ros:latest bash -c \
#     "source /opt/ros/humble/setup.bash && colcon build"
```

## 开发重点
1. 视觉跟随 (YOLO + depth → cmd_vel)
2. 障碍物规避 (depth + LiDAR)
3. 语音交互 (见 voice/ 模块)
4. SLAM 建图与导航 (slam/ + navigation/)
