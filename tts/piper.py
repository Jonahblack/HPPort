"""
Piper TTS engine implementation.
Runs fast local neural text-to-speech using Piper binary and ONNX models on Raspberry Pi 5 / PC.
Computes frame-by-frame audio RMS amplitude curves for synchronized Pygame mouth animation.
"""

import io
import logging
import math
import os
from pathlib import Path
import struct
import subprocess
import threading
import time
from typing import Callable, List, Optional
import wave

from .base import BaseTTS, TTSAudioResult, TTSMetrics

logger = logging.getLogger(__name__)


class PiperTTS(BaseTTS):
    """Local Piper TTS integration for low-latency voice synthesis on Raspberry Pi 5."""

    def __init__(
        self,
        piper_binary_path: str = "piper",
        model_path: str = "en_US-ryan-high.onnx",
        model_config_path: Optional[str] = None,
        speaker_id: int = 0,
        length_scale: float = 1.0,
        sample_rate: int = 22050,
    ):
        self.piper_binary_path = piper_binary_path
        self.model_path = model_path
        self.model_config_path = model_config_path or (model_path + ".json")
        self.speaker_id = speaker_id
        self.length_scale = length_scale
        self.sample_rate = sample_rate

        self._playback_thread: Optional[threading.Thread] = None
        self._stop_playback_event = threading.Event()

    def _extract_amplitudes(self, wav_bytes: bytes, frame_duration_ms: int = 33) -> List[float]:
        """Calculate normalized RMS amplitudes across the audio in ~30fps video slices."""
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                rate = wf.getframerate()
                nframes = wf.getnframes()
                raw_data = wf.readframes(nframes)

            samples_per_slice = int(rate * (frame_duration_ms / 1000.0))
            if sampwidth != 2:
                # Fallback simple scale
                return [0.3] * max(1, nframes // max(1, samples_per_slice))

            fmt = f"<{len(raw_data)//2}h"
            ints = struct.unpack(fmt, raw_data)

            # If stereo, average channels
            if channels > 1:
                ints = [(ints[i] + ints[i + 1]) // 2 for i in range(0, len(ints) - 1, 2)]

            amplitudes = []
            for i in range(0, len(ints), samples_per_slice):
                chunk = ints[i : i + samples_per_slice]
                if not chunk:
                    continue
                sum_sq = sum(s * s for s in chunk)
                rms = math.sqrt(sum_sq / len(chunk))
                # Normalize 16-bit audio RMS to 0.0 - 1.0 range
                norm = min(1.0, rms / 12000.0)
                amplitudes.append(round(norm, 3))

            return amplitudes or [0.0]
        except Exception as e:
            logger.warning("Error calculating audio amplitudes: %s", e)
            return [0.2, 0.5, 0.8, 0.4, 0.1]

    def synthesize(self, text: str, output_path: Optional[str] = None) -> TTSAudioResult:
        start_time = time.time()
        text_clean = text.strip()

        # Check if Piper binary exists
        if not Path(self.piper_binary_path).exists() and not Path(self.model_path).exists():
            logger.warning("Piper binary or model not found at %s. Operating in simulated TTS mode.", self.model_path)
            # Simulated Piper waveform output
            dur = max(1.2, len(text_clean) * 0.065)
            amplitudes = [abs(math.sin(i * 0.4)) * 0.7 + 0.1 for i in range(int(dur * 30))]
            metrics = TTSMetrics(
                generation_time_seconds=0.15,
                time_to_first_audio_seconds=0.08,
                audio_duration_seconds=dur,
            )
            return TTSAudioResult(
                audio_path=output_path,
                raw_pcm=b"",
                sample_rate=self.sample_rate,
                amplitudes=amplitudes,
                metrics=metrics,
            )

        cmd = [
            self.piper_binary_path,
            "--model", self.model_path,
            "--config", self.model_config_path,
            "--speaker", str(self.speaker_id),
            "--length-scale", str(self.length_scale),
            "--output-raw",
        ]

        if output_path:
            cmd.extend(["--output_file", output_path])

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_data, stderr_data = proc.communicate(input=text_clean.encode("utf-8"))

        gen_time = time.time() - start_time
        amplitudes = self._extract_amplitudes(stdout_data) if stdout_data else []
        dur = len(stdout_data) / (self.sample_rate * 2) if stdout_data else 1.0

        metrics = TTSMetrics(
            generation_time_seconds=gen_time,
            time_to_first_audio_seconds=gen_time * 0.6,
            audio_duration_seconds=dur,
        )
        logger.info("Piper synthesized speech in %.2fs (audio length: %.2fs)", gen_time, dur)

        return TTSAudioResult(
            audio_path=output_path,
            raw_pcm=stdout_data,
            sample_rate=self.sample_rate,
            amplitudes=amplitudes,
            metrics=metrics,
        )

    def play_audio(
        self,
        audio_result: TTSAudioResult,
        amplitude_callback: Optional[Callable[[float], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        self.stop_playback()
        self._stop_playback_event.clear()

        def _player():
            amps = audio_result.amplitudes or [0.0]
            step_dt = 0.033  # ~30 Hz frame rate sync

            # In hardware, play via pygame.mixer or aplay
            try:
                import pygame
                if pygame.mixer.get_init() and audio_result.audio_path and os.path.exists(audio_result.audio_path):
                    pygame.mixer.music.load(audio_result.audio_path)
                    pygame.mixer.music.play()
            except Exception:
                pass

            for amp in amps:
                if self._stop_playback_event.is_set():
                    break
                if amplitude_callback:
                    amplitude_callback(amp)
                time.sleep(step_dt)

            if amplitude_callback:
                amplitude_callback(0.0)

            if not self._stop_playback_event.is_set() and on_finished:
                on_finished()

        self._playback_thread = threading.Thread(target=_player, daemon=True)
        self._playback_thread.start()

    def stop_playback(self) -> None:
        self._stop_playback_event.set()
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.5)
