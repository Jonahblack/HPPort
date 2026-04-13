import audioop
import io
import os
import tempfile
import time
import wave
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pygame

try:
    from google.cloud import texttospeech as tts
except Exception:  # pragma: no cover - runtime dependency
    tts = None


LevelCallback = Callable[[float], None]


@dataclass
class SynthesizedSpeech:
    wav_bytes: bytes
    envelope: List[float]
    duration_seconds: float


class AudioPlayer:
    def __init__(self, config: dict, credentials_path: str = ""):
        self.config = config
        self.credentials_path = credentials_path
        self._tts_client = None
        self._initialized = False
        self._ensure_audio_ready()

    def _ensure_audio_ready(self) -> None:
        if self._initialized:
            return
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)
        volume = float(self.config.get("tts_volume", 1.0))
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        self._initialized = True

    def _get_tts_client(self):
        if tts is None:
            raise RuntimeError("google-cloud-texttospeech is not installed.")
        if self._tts_client is None:
            if self.credentials_path:
                os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", self.credentials_path)
            self._tts_client = tts.TextToSpeechClient()
        return self._tts_client

    def synthesize(self, text: str, language_code: str) -> SynthesizedSpeech:
        client = self._get_tts_client()
        voice_name = str(self.config.get("tts_voice_name", "")).strip()
        voice = tts.VoiceSelectionParams(language_code=language_code)
        if voice_name:
            voice.name = voice_name

        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            speaking_rate=float(self.config.get("tts_speaking_rate", 1.0)),
            pitch=float(self.config.get("tts_pitch", 0.0)),
        )
        response = client.synthesize_speech(
            input=tts.SynthesisInput(text=text),
            voice=voice,
            audio_config=audio_config,
        )
        envelope, duration = self._build_envelope(response.audio_content)
        return SynthesizedSpeech(response.audio_content, envelope, duration)

    def speak(self, speech: SynthesizedSpeech, on_level: Optional[LevelCallback] = None) -> None:
        if on_level:
            on_level(0.0)

        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        try:
            handle.write(speech.wav_bytes)
            handle.flush()
            handle.close()
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            pygame.mixer.music.load(handle.name)
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                if on_level:
                    pos_ms = max(0, pygame.mixer.music.get_pos())
                    index = min(int(pos_ms / 50), max(len(speech.envelope) - 1, 0))
                    level = speech.envelope[index] if speech.envelope else 0.65
                    on_level(level)
                time.sleep(0.05)
        finally:
            if on_level:
                on_level(0.0)
            try:
                os.unlink(handle.name)
            except Exception:
                pass

    def close(self) -> None:
        try:
            pygame.mixer.quit()
        except Exception:
            pass

    @staticmethod
    def _build_envelope(wav_bytes: bytes) -> Tuple[List[float], float]:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            window_frames = max(int(frame_rate * 0.05), 1)
            total_frames = wav_file.getnframes()
            duration = total_frames / float(frame_rate)
            levels: List[float] = []

            while True:
                chunk = wav_file.readframes(window_frames)
                if not chunk:
                    break
                rms = audioop.rms(chunk, sample_width)
                levels.append(min(1.0, rms / 12000.0))

        return levels, duration
