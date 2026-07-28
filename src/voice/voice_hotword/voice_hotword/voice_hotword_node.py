#!/usr/bin/env python3
"""
voice_hotword_node.py

Hotword detection and command routing using Vosk NFST grammar mode.
Three-tier pipeline:
  1. Vosk audio-level matching (16 phrases, ~50ms, no GPU)
  2. Whisper text-level secondary matching (via /voice/asr_result)
  3. LLM placeholder (future)

State machine:
  SLEEPING → "小车小车" → WAKE (蜂鸣800Hz + 5s timer)
  WAKE → command match → execute + reset timer
  WAKE → no match → forward audio to ASR
  WAKE → timeout/"休眠" → SLEEPING
"""

import json
import os
import time
import wave
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String, Float32MultiArray
from voice_msgs.msg import VoiceCommand
from ros_robot_controller_msgs.msg import BuzzerState
from builtin_interfaces.msg import Time as TimeMsg

# ── Phrase → command mapping ─────────────────────────────────────
PHRASE_MAP = {
    "前进":   ("motor", {"direction": "forward"}),
    "后退":   ("motor", {"direction": "backward"}),
    "向左":   ("motor", {"direction": "left"}),
    "向右":   ("motor", {"direction": "right"}),
    "左转":   ("motor", {"direction": "rotate_left"}),
    "右转":   ("motor", {"direction": "rotate_right"}),
    "停止":   ("motor", {"direction": "stop"}),
    "看左边": ("servo", {"pan": "left"}),
    "看右边": ("servo", {"pan": "right"}),
    "回正":   ("servo", {"pan": "home"}),
    "过来":   ("follow", {"mode": "start"}),
    "跟着我": ("follow", {"mode": "start"}),
    "回去":   ("navigation", {"mode": "return_home"}),
    "蜂鸣":   ("buzzer", {"mode": "short"}),
    "休眠":   ("_deactivate", {}),
    "小车小车": ("_wake", {}),
}

ALL_PHRASES = list(PHRASE_MAP.keys())


class VoiceHotwordNode(Node):
    STATE_SLEEPING = "sleeping"
    STATE_WAKE = "wake"
    STATE_LISTEN = "listen"

    def __init__(self):
        super().__init__("voice_hotword")

        # Parameters
        self.sample_rate = self.declare_parameter("sample_rate", 16000).value
        vosk_model_path = self.declare_parameter("vosk_model_path", "~/vosk-model-small-cn-0.22").value
        self.wake_timeout = self.declare_parameter("wake_timeout", 5.0).value
        self._clip_save_dir = self.declare_parameter("clip_save_dir", "/tmp/vosk_clips").value
        self._clip_save_enabled = self.declare_parameter("clip_save_enabled", True).value

        # State
        self._state = self.STATE_SLEEPING
        self._wake_timer = None
        self._last_wake_time = 0.0

        # Vosk model
        self._vosk_model = None
        self._load_vosk_model(os.path.expanduser(vosk_model_path))

        # Publishers
        self._wake_pub = self.create_publisher(Bool, "/voice/wake", 10)
        self._cmd_pub = self.create_publisher(VoiceCommand, "/voice/voice_command", 10)
        self._state_pub = self.create_publisher(String, "/voice/state", 10)
        self._asr_fwd_pub = self.create_publisher(Float32MultiArray, "/voice/audio_for_asr", 10)
        self._buzzer_pub = self.create_publisher(BuzzerState, "/ros_robot_controller/set_buzzer", 10)

        # Subscribers
        self._clip_sub = self.create_subscription(
            Float32MultiArray, "/voice/audio_clip", self.audio_clip_callback, 10
        )
        self._asr_sub = self.create_subscription(
            String, "/voice/asr_result", self.asr_result_callback, 10
        )

        self.get_logger().info(
            f"VoiceHotwordNode started: state=SLEEPING, "
            f"vosk_model={vosk_model_path}, phrases={len(ALL_PHRASES)}"
        )

    # ── Vosk model loading ────────────────────────────────────────
    def _load_vosk_model(self, model_path: str):
        try:
            from vosk import Model, KaldiRecognizer
            if os.path.exists(model_path):
                self._vosk_model = Model(model_path)
                self.get_logger().info(f"Vosk model loaded: {model_path}")
            else:
                self.get_logger().error(
                    f"Vosk model not found at {model_path}. "
                    f"Download from: "
                    f"https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip"
                )
        except Exception as e:
            self.get_logger().error(f"Failed to load Vosk: {e}")

    def _make_recognizer(self):
        """Create a Vosk recognizer in non-grammar mode (free dictation)."""
        if self._vosk_model is None:
            return None
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self._vosk_model, self.sample_rate)
        rec.SetWords(False)
        return rec

    # ── Publish helpers ───────────────────────────────────────────
    def _pub_buzzer(self, freq: int, duration: float):
        msg = BuzzerState()
        msg.freq = freq
        msg.on_time = duration
        msg.off_time = 0.01
        msg.repeat = 1
        self._buzzer_pub.publish(msg)

    def _pub_wake(self, wake: bool):
        msg = Bool()
        msg.data = wake
        self._wake_pub.publish(msg)

    def _pub_state(self, state: str):
        msg = String()
        msg.data = state
        self._state_pub.publish(msg)

    def _pub_command(self, phrase: str):
        action, params = PHRASE_MAP[phrase]
        msg = VoiceCommand()
        msg.command_text = phrase
        msg.confidence = 1.0
        msg.keywords = [phrase]
        # Build timestamp
        now = self.get_clock().now()
        msg.timestamp = TimeMsg(
            sec=int(now.nanoseconds // 1_000_000_000),
            nanosec=int(now.nanoseconds % 1_000_000_000),
        )
        self._cmd_pub.publish(msg)
        self.get_logger().info(f"Command: action={action} params={params}")

    # ── Buzzer feedback ───────────────────────────────────────────
    def _buzzer_wake(self):
        self._pub_buzzer(800, 0.10)

    def _buzzer_sleep(self):
        self._pub_buzzer(400, 0.05)

    def _buzzer_ack(self):
        self._pub_buzzer(600, 0.05)

    # ── Wake timer ────────────────────────────────────────────────
    def _reset_wake_timer(self):
        if self._wake_timer is not None:
            self._wake_timer.cancel()
        self._wake_timer = self.create_timer(self.wake_timeout, self._on_timeout)

    def _on_timeout(self):
        if self._state != self.STATE_SLEEPING:
            self.get_logger().info("Wake timeout — going to sleep")
            self._go_to_sleep()

    # ── State transitions ─────────────────────────────────────────
    def _wake_up(self):
        self._state = self.STATE_WAKE
        self._pub_wake(True)
        self._pub_state(self.STATE_WAKE)
        self._buzzer_wake()
        self._reset_wake_timer()
        self.get_logger().info("Woke up — listening for commands")

    def _go_to_sleep(self):
        self._state = self.STATE_SLEEPING
        self._pub_wake(False)
        self._pub_state(self.STATE_SLEEPING)
        self._buzzer_sleep()
        if self._wake_timer is not None:
            self._wake_timer.cancel()
            self._wake_timer = None
        self.get_logger().info("Sleeping")

    # ── Audio clip saving (debug) ────────────────────────────────
    def _save_audio_clip(self, audio: np.ndarray, tag: str):
        """Save raw audio as WAV for offline listening / debugging."""
        if not self._clip_save_enabled:
            return
        d = self._clip_save_dir
        try:
            os.makedirs(d, exist_ok=True)
            t = time.strftime("%H%M%S")
            safe_tag = tag.replace(" ", "_")[:24] or "empty"
            path = os.path.join(d, f"vosk_{t}_{safe_tag}.wav")
            audio_int16 = (audio * 32767).astype(np.int16)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_int16.tobytes())
            self.get_logger().debug(f"Clip saved: {path}")
        except Exception as e:
            self.get_logger().warn(f"Clip save failed: {e}")

    # ── Vosk audio matching ───────────────────────────────────────
    def _match_audio(self, audio_clip: np.ndarray) -> str | None:
        """Feed audio clip to Vosk, return matched phrase or None."""
        rec = self._make_recognizer()
        if rec is None:
            return None

        # Convert float32 to int16 (Vosk expects int16 PCM)
        audio_int16 = (audio_clip * 32767).astype(np.int16).tobytes()

        # Feed in chunks for better recognition
        chunk_size = self.sample_rate // 10  # 100ms chunks
        for i in range(0, len(audio_int16), chunk_size * 2):  # 2 bytes per sample
            chunk = audio_int16[i:i + chunk_size * 2]
            if len(chunk) < 2:
                break
            rec.AcceptWaveform(chunk)

        # Try final result
        result = json.loads(rec.FinalResult())
        text = result.get("text", "").strip()
        self._save_audio_clip(audio_clip, text if text else "no_match")
        if text:
            self.get_logger().info(f'Vosk heard: "{text}"')
            for phrase in ALL_PHRASES:
                if phrase in text:
                    return phrase
            return None  # Heard something but not a hotword
        else:
            self.get_logger().info("Vosk returned empty result")
        return None

    # ── Callbacks ─────────────────────────────────────────────────
    def audio_clip_callback(self, msg: Float32MultiArray):
        if not msg.data:
            return
        audio = np.array(msg.data, dtype=np.float32)
        phrase = self._match_audio(audio)

        if self._state == self.STATE_SLEEPING:
            # Only "小车小车" is accepted in SLEEPING
            if phrase == "小车小车":
                self._wake_up()
            # Everything else is silently discarded
            return

        # STATE_WAKE
        if phrase is None:
            # No Vosk match — forward to ASR
            self._state = self.STATE_LISTEN
            self._pub_state(self.STATE_LISTEN)
            self._asr_fwd_pub.publish(msg)  # forward raw Float32MultiArray
            self.get_logger().debug("No Vosk match — forwarded to ASR")
            return

        # Matched a phrase
        if phrase == "小车小车":
            # Already awake, just reset timer
            self._reset_wake_timer()
            return
        elif phrase == "休眠":
            self._go_to_sleep()
            return
        else:
            self._pub_command(phrase)
            self._buzzer_ack()
            self._reset_wake_timer()

    def asr_result_callback(self, msg: String):
        """Text-level secondary matching from Whisper."""
        if self._state == self.STATE_SLEEPING:
            return
        text = msg.data.strip()
        if not text:
            # Back to waiting
            self._state = self.STATE_WAKE
            self._pub_state(self.STATE_WAKE)
            return

        for phrase in ALL_PHRASES:
            if phrase in text:
                if phrase == "小车小车":
                    self._reset_wake_timer()
                    break
                elif phrase == "休眠":
                    self._go_to_sleep()
                    return
                else:
                    self._pub_command(phrase)
                    self._buzzer_ack()
                    break

        # Back to WAKE state
        self._state = self.STATE_WAKE
        self._pub_state(self.STATE_WAKE)
        self._reset_wake_timer()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceHotwordNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
