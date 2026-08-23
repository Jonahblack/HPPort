"""Piper local neural TTS engine driver for Raspberry Pi 5 / Desktop."""

import os
import shutil
import subprocess
import time
import wave
from typing import Tuple, Dict, Any
from tts.base import BaseTTS


class PiperTTS(BaseTTS):
    """Executes Piper binary to output 16-bit 22.05kHz WAV."""

    def __init__(self, config: Dict[str, Any]):
        tts_cfg = config.get("tts", {})
        self.piper_binary = tts_cfg.get("piper_binary_path", "/mnt/portrait/models/piper/piper")
        self.model_path = tts_cfg.get("model_path", "/mnt/portrait/models/piper/en_US-ryan-high.onnx")
        self.model_config = tts_cfg.get("model_config_path", "/mnt/portrait/models/piper/en_US-ryan-high.onnx.json")
        self.speaker_id = int(tts_cfg.get("speaker_id", 0))
        self.length_scale = float(tts_cfg.get("length_scale", 1.0))
        self.noise_scale = float(tts_cfg.get("noise_scale", 0.667))
        self.noise_w = float(tts_cfg.get("noise_w", 0.8))

        # Check binary location
        self._find_piper()

    def _find_piper(self) -> None:
        """Find Piper executable across standard locations."""
        candidates = [
            self.piper_binary,
            shutil.which("piper"),
            os.path.expanduser("~/piper/piper"),
            "./models/piper/piper",
            "/usr/local/bin/piper",
            "/usr/bin/piper",
        ]
        for path in candidates:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                self.piper_binary = path
                print(f"[TTS] Located Piper executable: {self.piper_binary}")
                return

        print(f"[TTS] Notice: Piper executable not found at {self.piper_binary}. Will use audio synthesizer fallback if needed.")

    def synthesize_to_file(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)
        start_time = time.time()

        if os.path.exists(self.piper_binary) and os.path.exists(self.model_path):
            cmd = [
                self.piper_binary,
                "--model", self.model_path,
                "--output_file", output_wav_path,
                "--speaker", str(self.speaker_id),
                "--length_scale", str(self.length_scale),
                "--noise_scale", str(self.noise_scale),
                "--noise_w", str(self.noise_w),
            ]
            if os.path.exists(self.model_config):
                cmd.extend(["--config", self.model_config])

            try:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stdout, stderr = process.communicate(input=text)

                if process.returncode == 0 and os.path.exists(output_wav_path):
                    duration = self._get_wav_duration(output_wav_path)
                    synth_time = time.time() - start_time
                    print(f"[TTS] Piper generated '{output_wav_path}' in {synth_time:.2f}s (Audio duration: {duration:.2f}s)")
                    return output_wav_path, duration
                else:
                    print(f"[TTS] Piper returned code {process.returncode}: {stderr}")
            except Exception as e:
                print(f"[TTS] Piper execution error: {e}")

        # Fallback to pure Python synthesized waveform
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
