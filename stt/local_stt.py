"""Local STT driver using Faster-Whisper and SpeechRecognition on Raspberry Pi 5 / Desktop."""

import time
import os
import io
import wave
from typing import Dict, Any, Optional
from stt.base import BaseSTT


class LocalSTT(BaseSTT):
    """Faster-Whisper on CPU with INT8 quantization & live microphone recording."""

    def __init__(self, config: Dict[str, Any]):
        stt_cfg = config.get("stt", {})
        self.model_size = stt_cfg.get("model_size", "tiny.en")
        self.language = stt_cfg.get("language", "en")
        self.device = stt_cfg.get("device", "cpu")
        self.compute_type = stt_cfg.get("compute_type", "int8")
        self.vad_filter = stt_cfg.get("vad_filter", True)
        self.energy_threshold = int(stt_cfg.get("energy_threshold", 300))

        self.model = None
        self.recognizer = None
        self.microphone = None
        self._mic_available = False

        self._init_audio_input()
        self._init_model()

    def _init_audio_input(self) -> None:
        """Initialize SpeechRecognition microphone."""
        try:
            import speech_recognition as sr  # type: ignore
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = self.energy_threshold
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
            self.microphone = sr.Microphone()
            self._mic_available = True
            print("[STT] SpeechRecognition microphone initialized.")
        except Exception as e:
            print(f"[STT] Notice: USB microphone not detected ({e}).")
            self._mic_available = False

    def _init_model(self) -> None:
        """Load faster-whisper model."""
        try:
            from faster_whisper import WhisperModel  # type: ignore
            print(f"[STT] Loading faster-whisper model '{self.model_size}' ({self.compute_type})...")
            self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            print("[STT] Faster-Whisper model ready.")
        except Exception as e:
            print(f"[STT] Faster-whisper model load notice ({e}). Using lightweight recognizer.")
            self.model = None

    def listen_and_transcribe(self, timeout_seconds: float = 3.0, max_duration_seconds: float = 10.0) -> Optional[str]:
        """Record spoken audio from microphone and transcribe to text."""
        if not self._mic_available or not self.recognizer or not self.microphone:
            print("[STT] Microphone not available. Simulating brief listening wait (or press 'T' in window)...")
            time.sleep(1.2)
            return None

        import speech_recognition as sr  # type: ignore

        print(f"[STT] 🎙️ Listening for user speech (Timeout: {timeout_seconds}s, Max: {max_duration_seconds}s)...")
        start_time = time.time()

        try:
            with self.microphone as source:
                # Adjust for ambient noise briefly
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio_data = self.recognizer.listen(
                    source,
                    timeout=timeout_seconds,
                    phrase_time_limit=max_duration_seconds,
                )

            record_duration = time.time() - start_time
            print(f"[STT] Audio captured in {record_duration:.2f}s. Transcribing...")

            # 1. Try Faster-Whisper if loaded
            if self.model is not None:
                wav_bytes = audio_data.get_wav_data()
                wav_file = io.BytesIO(wav_bytes)
                segments, info = self.model.transcribe(
                    wav_file,
                    beam_size=1,
                    language=self.language,
                    vad_filter=self.vad_filter,
                )
                text = " ".join([segment.text for segment in segments]).strip()
                if text:
                    dur = time.time() - start_time
                    print(f"[STT] Faster-Whisper ({dur:.2f}s): \"{text}\"")
                    return text

            # 2. Fallback to Google speech recognizer
            text = self.recognizer.recognize_google(audio_data)
            dur = time.time() - start_time
            print(f"[STT] Transcribed ({dur:.2f}s): \"{text}\"")
            return text

        except sr.WaitTimeoutError:
            print("[STT] Silence / timeout (no speech detected).")
            return None
        except sr.UnknownValueError:
            print("[STT] Audio unclear / incomprehensible.")
            return None
        except Exception as e:
            print(f"[STT] Audio listen error: {e}")
            return None
