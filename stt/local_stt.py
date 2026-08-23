"""Local STT driver using faster-whisper on Raspberry Pi 5."""

import time
import os
from typing import Dict, Any, Optional
from stt.base import BaseSTT


class LocalSTT(BaseSTT):
    """Faster-Whisper on CPU with INT8 quantization."""

    def __init__(self, config: Dict[str, Any]):
        stt_cfg = config.get("stt", {})
        self.model_size = stt_cfg.get("model_size", "tiny.en")
        self.language = stt_cfg.get("language", "en")
        self.device = stt_cfg.get("device", "cpu")
        self.compute_type = stt_cfg.get("compute_type", "int8")
        self.vad_filter = stt_cfg.get("vad_filter", True)
        self.energy_threshold = int(stt_cfg.get("energy_threshold", 300))

        self.model = None
        self._init_model()

    def _init_model(self) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore
            print(f"[STT] Loading faster-whisper model '{self.model_size}' ({self.compute_type})...")
            self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            print("[STT] Faster-Whisper ready.")
        except Exception as e:
            print(f"[STT] Notice: faster-whisper not initialized in current environment ({e}).")

    def listen_and_transcribe(self, timeout_seconds: float = 2.0, max_duration_seconds: float = 10.0) -> Optional[str]:
        print(f"[STT] Listening for audio (timeout={timeout_seconds}s, max={max_duration_seconds}s)...")
        time.sleep(1.0)
        return None
