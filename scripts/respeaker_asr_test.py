#!/usr/bin/env python3
"""
ReSpeaker ASR 测试脚本 — 唤醒词门控语音识别

工作流程:
  睡眠模式 → 说 "hey jarvis" → 唤醒 → 说话 → whisper 识别 → 打印文字
                                          ↓ 静音 8s
                                      回到睡眠

用法:
  python3 scripts/respeaker_asr_test.py

依赖:
  pip3 install sounddevice numpy scipy openai-whisper openwakeword
"""

import sounddevice as sd
import numpy as np
import time
import sys
import whisper
from openwakeword.model import Model as WakeModel

# ═══════════════════════════ 参数 ═══════════════════════════
SAMPLE_RATE = 16000
CHUNK_MS = 50
CHUNK = int(SAMPLE_RATE * CHUNK_MS / 1000)

# ── 唤醒前: 高阈值，只检测唤醒词，省 GPU ──
WAKE_THRESHOLD = 0.035       # 能量阈值（~3× 环境噪声中位数）
WAKE_MODEL    = "hey_jarvis_v0.1"
WAKE_SCORE    = 0.5          # 唤醒词置信度门限

# ── 唤醒后: 低阈值，whisper 精准识别 ──
ASR_THRESHOLD       = 0.015  # 能量阈值
ASR_SILENCE_TIMEOUT = 0.8    # 沉默多久=句子结束(s)
ASR_MIN_SPEECH_MS   = 800    # 最短语音(ms)
ASR_MAX_SPEECH_MS   = 10000  # 最长语音(ms)
ASR_COOLDOWN        = 2.0    # 两次识别最小间隔(s)
WAKE_TIMEOUT        = 8.0    # 唤醒后无语音超时(s)
ASR_MODEL_SIZE      = "base" # tiny / base / small
ASR_LANGUAGE        = "zh"


# ═══════════════════════════ 设备 ═══════════════════════════
devices = sd.query_devices()
respeaker_idx = None
for i, d in enumerate(devices):
    name = d['name']
    if ('ArrayUAC10' in name or 'ReSpeaker' in name) and 'hw:' in name:
        respeaker_idx = i
        break
if respeaker_idx is not None:
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and ('ArrayUAC10' in d['name'] or 'ReSpeaker' in d['name']):
            respeaker_idx = i
            break

def die(msg):
    print(msg, file=sys.stderr)
    print("可用输入设备:", file=sys.stderr)
    for i, d in enumerate(sd.query_devices()):
        if d['max_input_channels'] > 0:
            print(f"  [{i}] {d['name']} ({d['max_input_channels']} in)", file=sys.stderr)
    sys.exit(1)

if respeaker_idx is None:
    die("找不到 ReSpeaker 设备！")
dev_info = devices[respeaker_idx]
n_ch = max(dev_info['max_input_channels'], 1)
print(f"[设备] [{respeaker_idx}] {dev_info['name']} ({n_ch} in)")


# ═══════════════════════════ 加载模型 ═══════════════════════════
sys.stdout.flush()
print(f"[模型] 加载唤醒词 ({WAKE_MODEL})...", end=" ")
wake_model = WakeModel(wakeword_models=[WAKE_MODEL])
wake_words = list(wake_model.models.keys())
print(f"→ 唤醒词: {', '.join(wake_words)}")

print(f"[模型] 加载 Whisper ({ASR_MODEL_SIZE})...", end=" ")
sys.stdout.flush()
asr_model = whisper.load_model(ASR_MODEL_SIZE, device="cuda")
print("→ 就绪！")


# ═══════════════════════════ VAD 状态 ═══════════════════════════
awake = False
last_activity = 0.0
buf = np.array([], dtype=np.float32)
speech_on = False
silence_n = 0
last_recog_t = 0.0
last_dot_t = time.time()
n_recog = 0


def do_asr(seg):
    global last_recog_t, n_recog
    if len(seg) < int(ASR_MIN_SPEECH_MS * SAMPLE_RATE / 1000):
        return
    now = time.time()
    if now - last_recog_t < ASR_COOLDOWN:
        return
    last_recog_t = now
    n_recog += 1

    rms = np.sqrt(np.mean(seg ** 2))
    if rms > 1e-6:
        seg = seg * (0.08 / rms)
    seg = np.clip(seg, -1.0, 1.0)

    dur = len(seg) / SAMPLE_RATE
    print(f"\n[{n_recog}] 识别 ({dur:.1f}s)...", end=" ", flush=True)
    try:
        result = asr_model.transcribe(seg, language=ASR_LANGUAGE, fp16=True, verbose=False)
        text = result.get('text', '').strip()
        print(f"→ {text}" if len(text) >= 2 else "→ (空)")
    except Exception as e:
        print(f"→ 失败: {e}")


def callback(indata, frames, time_info, status):
    global awake, last_activity, buf, speech_on, silence_n, last_recog_t, last_dot_t

    audio = indata[:, 0] if indata.shape[1] > 1 else indata.flatten().astype(np.float32)
    rms = np.sqrt(np.mean(audio ** 2))

    if awake:
        # ── 唤醒模式 ──
        talking = rms > ASR_THRESHOLD
        sl_max = int(ASR_SILENCE_TIMEOUT * SAMPLE_RATE / CHUNK)

        if talking:
            last_activity = time.time()
            if not speech_on:
                speech_on = True
                buf = np.array([], dtype=np.float32)
            buf = np.concatenate([buf, audio])
            silence_n = 0
        elif speech_on:
            buf = np.concatenate([buf, audio])
            silence_n += 1
            if silence_n >= sl_max or len(buf) > int(ASR_MAX_SPEECH_MS * SAMPLE_RATE / 1000):
                do_asr(buf)
                speech_on = False
                buf = np.array([], dtype=np.float32)
                silence_n = 0

        if time.time() - last_activity > WAKE_TIMEOUT:
            awake = False
            speech_on = False
            buf = np.array([], dtype=np.float32)
            silence_n = 0
            print("\n💤 超时 → 睡眠")
        ch = "▫" if talking else "▪"

    else:
        # ── 睡眠模式 ──
        if rms > WAKE_THRESHOLD:
            scores = wake_model.predict(audio)
            for ww, sc in scores.items():
                if sc > WAKE_SCORE:
                    print(f"\n🔊 [{ww}] {sc:.3f}")
                    awake = True
                    last_activity = time.time()
                    speech_on = False
                    buf = np.array([], dtype=np.float32)
                    silence_n = 0
                    print("🎤 唤醒！请说话...")
                    break
            wake_model.reset()
        ch = "○"
        speech_on = False
        buf = np.array([], dtype=np.float32)
        silence_n = 0

    if time.time() - last_dot_t > 0.3:
        sys.stdout.write(ch)
        sys.stdout.flush()
        last_dot_t = time.time()


# ═══════════════════════════ 主循环 ═══════════════════════════
if __name__ == '__main__':
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=n_ch,
            blocksize=CHUNK,
            device=respeaker_idx,
            dtype='float32',
            callback=callback,
        ):
            print(f"○ {' '.join(wake_words)} 等待中…")
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n结束")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback; traceback.print_exc()
