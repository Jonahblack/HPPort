"""
Local Speech-to-Text (STT) implementation using Faster-Whisper or Whisper.cpp.
Designed to run on Raspberry Pi 5 CPU offline with VAD endpointing.
"""

import logging
import queue
import threading
import time
from typing import Callable, Optional

from .base import BaseSTT, STTResult

logger = logging.getLogger(__name__)


class LocalSTT(BaseSTT):
    """Local offline STT processor using faster-whisper on Raspberry Pi 5 / PC."""

    def __init__(
        self,
        model_size: str = "tiny.en",
        language: str = "en",
        device: str = "cpu",
        compute_type: str = "int8",
        energy_threshold: int = 300,
        silence_timeout_seconds: float = 2.0,
        max_duration_seconds: float = 10.0,
    ):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.energy_threshold = energy_threshold
        self.silence_timeout_seconds = silence_timeout_seconds
        self.max_duration_seconds = max_duration_seconds

        self._model = None
        self._is_listening = False
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._callback: Optional[Callable[[STTResult], None]] = None
        self._silence_callback: Optional[Callable[[], None]] = None

    def _lazy_init_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info("Initializing faster-whisper model (%s, %s, %s)...", self.model_size, self.device, self.compute_type)
                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root="/mnt/portrait/models/stt" if self.device == "cpu" else None,
                )
            except ImportError:
                logger.warning("faster-whisper not installed; LocalSTT will operate with simulated transcription.")
                self._model = "fallback"

    def is_listening(self) -> bool:
        return self._is_listening

    def start_listening(self, callback: Callable[[STTResult], None], on_silence: Optional[Callable[[], None]] = None) -> None:
        if self._is_listening:
            return

        self._lazy_init_model()
        self._callback = callback
        self._silence_callback = on_silence
        self._is_listening = True
        self._stop_event.clear()

        self._listen_thread = threading.Thread(target=self._recording_worker, daemon=True)
        self._listen_thread.start()
        logger.info("LocalSTT started listening.")

    def stop_listening(self) -> None:
        self._is_listening = False
        self._stop_event.set()
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=1.0)
        logger.info("LocalSTT stopped listening.")

    def _recording_worker(self) -> None:
        """Record audio until endpointing silence or max duration, then transcribe."""
        start_time = time.time()
        # In hardware mode, capture audio frames via sounddevice/pyaudio.
        # Fallback simulation if sounddevice is not present on dev environment.
        try:
            import sounddevice as sd
            import numpy as np

            samplerate = 16000
            channels = 1
            audio_buffer = []
            silence_start = None

            with sd.InputStream(samplerate=samplerate, channels=channels, dtype="int16") as stream:
                while not self._stop_event.is_set():
                    data, _ = stream.read(1024)
                    audio_buffer.append(data)
                    rms = np.sqrt(np.mean(data**2)) if len(data) > 0 else 0

                    if rms < self.energy_threshold:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start > self.silence_timeout_seconds and len(audio_buffer) > 15:
                            # User stopped speaking
                            break
                    else:
                        silence_start = None

                    if time.time() - start_time > self.max_duration_seconds:
                        break

            if self._stop_event.is_set():
                return

            if audio_buffer:
                raw_audio = np.concatenate(audio_buffer, axis=0).astype(np.float32) / 32768.0
                text = self._transcribe_array(raw_audio)
                duration = time.time() - start_time
                if text.strip() and self._callback:
                    self._callback(STTResult(text=text.strip(), duration_seconds=duration))
                elif self._silence_callback:
                    self._silence_callback()
        except Exception as e:
            logger.debug("Microphone recording unavailable or ended: %s. Using simulated utterance.", e)
            time.sleep(1.0)
            if not self._stop_event.is_set() and self._callback:
                self._callback(STTResult(text="Hello noble portrait! What secrets do you guard?", duration_seconds=1.0))

    def _transcribe_array(self, audio_data) -> str:
        if self._model and self._model != "fallback":
            segments, _ = self._model.transcribe(audio_data, language=self.language, vad_filter=True)
            return " ".join([segment.text for segment in segments])
        return "Greetings from the living world!"

    def transcribe_file(self, audio_path: str) -> STTResult:
        self._lazy_init_model()
        start = time.time()
        if self._model and self._model != "fallback":
            segments, _ = self._model.transcribe(audio_path, language=self.language)
            text = " ".join([segment.text for segment in segments])
            return STTResult(text=text, duration_seconds=time.time() - start)
        return STTResult(text="Sample audio transcription", duration_seconds=0.2)
