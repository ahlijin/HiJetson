# 更新日志

## [v0.5.0] — 2026-07-28

### 新增
- 双唤醒词："小车小车"(Vosk语法模式) + "小方小方"(ASR直通模式)
- Vosk 语法模式：字符空格分隔 + [unk] silence 吸收，只匹配 19 个短语
- "向前"/"向后" 作为"前进"/"后退"的同义短语
- "退出" 替代"休眠"，Vosk/ASR 模式均有效
- ASR 模式中 退出 指令优先级高于 Whisper 转发
- Epoch 隔离机制：防止前一轮慢 ASR 结果污染当前状态
- VAD 前缀环形缓冲（prefix_frames=10），解决首字裁切
- 不同唤醒词使用不同蜂鸣（800Hz vs 1000+800Hz）

### 变更
- Vosk 转为语法模式，不再做自由转录
- Vosk 模式下无匹配不再走 ASR 兜底，改为静默忽略
- servo_tracker 角度范围从 ±90° 改为 ±45°
- clip_save_enabled 默认 false（代码保留）

### 修复
- Vosk 语法模式中文空格分隔，避免全部识别为"向右"
- 唤醒词蜂鸣不重复（从 _wake_up 移到回调）
- 状态机处理静默期超时正确退出 ASR 模式

## [v0.4.0] — 2026-07-27

### 新增
- 三阶语音管线：Vosk 热词 → Whisper ASR → LLM（预留）
- voice_hotword 包（Vosk NFST 匹配 + 指令路由）
- 音频调试保存功能（clip_save_dir）
- hidraw 后端支持 XVF3000 DOA（避免 pyusb 踢掉 ALSA）

### 变更
- voice_asr 精简，去除唤醒/指令解析
- Launch 文件替换 voice_wake_word → voice_hotword
- voice_doa 后端默认 hidraw

### 已知问题
- Vosk vosk-model-small-cn-0.22 准确率待优化
- DOA hidraw 后端需要 libhidapi-libusb0

## [v0.3.0] — 2026-07-09

### 新增
- 语音管线完整部署：capture → VAD → 唤醒 → ASR → 反馈
- 能量 VAD 静音超时控制
- 声源定位(DOA) + 舵机跟随
- 启动脚本自动加载 snd-usb-audio

### 修复
- ALSA 直连 PulseAudio 兼容
- VAD 参数校准
