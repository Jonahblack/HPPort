"""Piper local neural TTS engine driver for Raspberry Pi 5."""

import os
import subprocess
import time
import wave
from typing import Tuple, Dict, Any
from tts.base import BaseTTS


class PiperTTS(BaseTTS):
    """Executes Piper binary on Raspberry Pi 5 to output 16-bit 22.05kHz WAV."""

    def __init__(self, config: Dict[str, Any]):
        tts_cfg = config.get("tts", {})
        self.piper_binary = tts_cfg.get("piper_binary_path", "/mnt/portrait/models/piper/piper")
        self.model_path = tts_cfg.get("model_path", "/mnt/portrait/models/piper/en_US-ryan-high.onnx")
        self.model_config = tts_cfg.get("model_config_path", "/mnt/portrait/models/piper/en_US-ryan-high.onnx.json")
        self.speaker_id = int(tts_cfg.get("speaker_id", 0))
        self.length_scale = float(tts_cfg.get("length_scale", 1.0))
        self.noise_scale = float(tts_cfg.get("noise_scale", 0.667))
        self.noise_w = float(tts_cfg.get("noise_w", 0.8))

    def synthesize_to_file(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)
        start_time = time.time()

        cmd = [
            self.piper_binary,
            "--model", self.model_path,
            "--config", self.model_config,
            "--output_file", output_wav_path,
            "--speaker", str(self.speaker_id),
            "--length_scale", str(self.length_scale),
            "--noise_scale", str(self.noise_scale),
            "--noise_w", str(self.noise_w),
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(input=text)

            if process.returncode != 0:
                print(f"[TTS] Piper error ({process.returncode}): {stderr}")
                return self._create_fallback_audio(output_wav_path, text)

            duration = self._get_wav_duration(output_wav_path)
            synth_time = time.time() - start_time
            print(f"[TTS] Piper synthesized in {synth_time:.2f}s (Audio duration: {duration:.2f}s)")
            return output_wav_path, duration
        except FileNotFoundError:
            print(f"[TTS] Piper binary not found at {self.piper_binary}. Using fallback tone.")
            return self._create_fallback_audio(output_wav_path, text)

    def _get_wav_duration(self, wav_path: str) -> float:
        try:
            with wave.open(wav_path, "r") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / float(rate)
        except Exception:
            return 2.0

    def _create_fallback_audio(self, wav_path: str, text: str) -> Tuple[str, float]:
        from tts.mock_tts import MockTTS
        mock = MockTTS()
        return mock.synthesize_to_file(text, wav_path)
