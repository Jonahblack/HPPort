"""Local STT driver using Faster-Whisper and SpeechRecognition on Raspberry Pi 5 / Desktop."""

import io
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

from stt.base import BaseSTT


class LocalSTT(BaseSTT):
    """Faster-Whisper on CPU with microphone auto-selection and arecord fallback."""

    OUTPUT_LIKE_KEYWORDS = (
        "monitor",
        "output",
        "speaker",
        "playback",
        "loopback",
        "hdmi",
        "headphone",
    )

    def __init__(self, config: Dict[str, Any]):
        stt_cfg = config.get("stt", {})
        self.model_size = stt_cfg.get("model_size", "tiny.en")
        self.language = stt_cfg.get("language", "en")
        self.device = stt_cfg.get("device", "cpu")
        self.compute_type = stt_cfg.get("compute_type", "int8")
        self.vad_filter = stt_cfg.get("vad_filter", True)
        self.energy_threshold = int(stt_cfg.get("energy_threshold", 300))
        self.dynamic_energy_threshold = bool(stt_cfg.get("dynamic_energy_threshold", True))
        self.ambient_calibration_seconds = float(stt_cfg.get("ambient_calibration_seconds", 0.3))
        self.microphone_device_index = self._coerce_optional_int(stt_cfg.get("microphone_device_index"))
        self.microphone_name = str(stt_cfg.get("microphone_name", "")).strip()
        self.sample_rate = self._coerce_optional_int(stt_cfg.get("sample_rate"))
        self.chunk_size = int(stt_cfg.get("chunk_size", 1024))
        self.arecord_device = str(stt_cfg.get("arecord_device", "")).strip()

        self.model = None
        self.recognizer = None
        self.microphone = None
        self._mic_available = False
        self._selected_device_index: Optional[int] = None
        self._selected_device_name = ""
        self._selected_sample_rate: Optional[int] = None
        self._use_arecord_fallback = False
        self._ambient_calibrated = False

        self._init_audio_input()
        self._init_model()

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _looks_output_like(cls, name: str) -> bool:
        lowered = name.lower()
        return any(keyword in lowered for keyword in cls.OUTPUT_LIKE_KEYWORDS)

    @classmethod
    def _choose_microphone_index(
        cls,
        names: List[str],
        configured_index: Optional[int] = None,
        configured_name: str = "",
        preferred_index: Optional[int] = None,
    ) -> Optional[int]:
        if configured_name:
            needle = configured_name.lower()
            for index, name in enumerate(names):
                if needle in name.lower():
                    return index

        if configured_index is not None and 0 <= configured_index < len(names):
            return configured_index

        if preferred_index is not None and 0 <= preferred_index < len(names):
            return preferred_index

        for index, name in enumerate(names):
            if name and not cls._looks_output_like(name):
                return index

        for index, name in enumerate(names):
            if name:
                return index

        return None

    def _default_input_index_from_sounddevice(self) -> Optional[int]:
        try:
            import sounddevice as sd  # type: ignore
        except Exception:
            return None

        try:
            default_device = sd.default.device
            if isinstance(default_device, (list, tuple)) and len(default_device) >= 1:
                input_index = default_device[0]
                if input_index is not None and int(input_index) >= 0:
                    return int(input_index)
        except Exception:
            return None

        return None

    def _list_audio_devices(self) -> List[str]:
        try:
            import speech_recognition as sr  # type: ignore

            return sr.Microphone.list_microphone_names()
        except Exception:
            return []

    def _device_sample_rate(self, device_index: Optional[int]) -> Optional[int]:
        if device_index is None:
            return None

        try:
            import sounddevice as sd  # type: ignore

            device_info = sd.query_devices(device_index)
            sample_rate = int(device_info.get("default_samplerate", 0) or 0)
            return sample_rate if sample_rate > 0 else None
        except Exception:
            return None

    def _resolve_arecord_device(self) -> str:
        if self.arecord_device:
            return self.arecord_device

        if not shutil.which("arecord"):
            return ""

        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except Exception:
            return ""

        configured_name = self.microphone_name.lower()
        pattern = re.compile(r"card\s+(\d+):.*?\[(.*?)\],\s*device\s+(\d+):", re.IGNORECASE)
        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if not match:
                continue

            card_index, card_name, device_index = match.groups()
            if configured_name and configured_name not in line.lower() and configured_name not in card_name.lower():
                continue

            return f"plughw:{card_index},{device_index}"

        return ""

    def _init_arecord_fallback(self, reason: str) -> None:
        resolved_device = self._resolve_arecord_device()
        if not resolved_device:
            print(f"[STT] arecord fallback unavailable ({reason}).")
            return

        self._use_arecord_fallback = True
        self._mic_available = True
        self.arecord_device = resolved_device
        self._selected_device_name = self.microphone_name or resolved_device
        self._selected_sample_rate = self.sample_rate or 16000
        print(
            f"[STT] Using arecord fallback "
            f"(device='{self.arecord_device}', sample_rate={self._selected_sample_rate}) because {reason}."
        )

    def _init_audio_input(self) -> None:
        """Initialize SpeechRecognition microphone with explicit device selection."""
        try:
            import speech_recognition as sr  # type: ignore

            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = self.energy_threshold
            self.recognizer.dynamic_energy_threshold = self.dynamic_energy_threshold
            self.recognizer.pause_threshold = 0.8

            device_names = self._list_audio_devices()
            preferred_index = self._default_input_index_from_sounddevice()
            selected_index = self._choose_microphone_index(
                device_names,
                configured_index=self.microphone_device_index,
                configured_name=self.microphone_name,
                preferred_index=preferred_index,
            )

            sample_rate = self.sample_rate or self._device_sample_rate(selected_index) or 16000
            microphone_kwargs = {"sample_rate": sample_rate, "chunk_size": self.chunk_size}
            if selected_index is not None:
                microphone_kwargs["device_index"] = selected_index

            self.microphone = sr.Microphone(**microphone_kwargs)
            self._mic_available = True
            self._selected_device_index = selected_index
            self._selected_device_name = (
                device_names[selected_index] if selected_index is not None and selected_index < len(device_names) else "default"
            )
            self._selected_sample_rate = sample_rate
            print(
                f"[STT] SpeechRecognition microphone initialized "
                f"(device={self._selected_device_index}, name='{self._selected_device_name}', sample_rate={sample_rate})."
            )
        except Exception as exc:
            self._mic_available = False
            device_names = self._list_audio_devices()
            print(f"[STT] Notice: microphone initialization failed ({exc}).")
            if device_names:
                for index, name in enumerate(device_names):
                    print(f"[STT]   device {index}: {name}")
            else:
                print("[STT]   no microphone devices reported by SpeechRecognition/PyAudio.")
            self._init_arecord_fallback(str(exc))

    def _init_model(self) -> None:
        """Load faster-whisper model."""
        try:
            from faster_whisper import WhisperModel  # type: ignore

            print(f"[STT] Loading faster-whisper model '{self.model_size}' ({self.compute_type})...")
            self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            print("[STT] Faster-Whisper model ready.")
        except Exception as exc:
            print(
                f"[STT] Faster-whisper model load notice ({exc}). "
                "Install it in this Python environment to enable transcription."
            )
            self.model = None

    def listen_and_transcribe(self, timeout_seconds: float = 3.0, max_duration_seconds: float = 10.0) -> Optional[str]:
        """Record spoken audio from microphone and transcribe to text."""
        if self._use_arecord_fallback:
            return self._listen_with_arecord(max_duration_seconds=max_duration_seconds)

        if not self._mic_available or not self.recognizer or not self.microphone:
            print("[STT] Microphone not available. Simulating brief listening wait (or press 'T' in window)...")
            time.sleep(1.2)
            return None

        import speech_recognition as sr  # type: ignore

        print(
            f"[STT] Listening for user speech "
            f"(device={self._selected_device_index}, timeout={timeout_seconds}s, max={max_duration_seconds}s)..."
        )
        start_time = time.time()

        try:
            with self.microphone as source:
                if not self._ambient_calibrated and self.ambient_calibration_seconds > 0:
                    self.recognizer.adjust_for_ambient_noise(
                        source,
                        duration=self.ambient_calibration_seconds,
                    )
                    self._ambient_calibrated = True
                    print(
                        f"[STT] Ambient calibration complete "
                        f"(energy_threshold={self.recognizer.energy_threshold:.0f})."
                    )
                audio_data = self.recognizer.listen(
                    source,
                    timeout=timeout_seconds,
                    phrase_time_limit=max_duration_seconds,
                )

            record_duration = time.time() - start_time
            print(f"[STT] Audio captured in {record_duration:.2f}s. Transcribing...")

            if self.model is not None:
                wav_bytes = audio_data.get_wav_data()
                wav_file = io.BytesIO(wav_bytes)
                segments, _info = self.model.transcribe(
                    wav_file,
                    beam_size=1,
                    language=self.language,
                    vad_filter=self.vad_filter,
                )
                text = " ".join(segment.text for segment in segments).strip()
                if text:
                    duration = time.time() - start_time
                    print(f"[STT] Faster-Whisper ({duration:.2f}s): \"{text}\"")
                    return text

            text = self.recognizer.recognize_google(audio_data)
            duration = time.time() - start_time
            print(f"[STT] Fallback recognizer ({duration:.2f}s): \"{text}\"")
            return text

        except sr.WaitTimeoutError:
            print("[STT] Silence / timeout (no speech detected).")
            return None
        except sr.UnknownValueError:
            print("[STT] Audio unclear / incomprehensible.")
            return None
        except Exception as exc:
            print(f"[STT] Audio listen error: {exc}")
            lowered = str(exc).lower()
            device_error_markers = (
                "invalid input device",
                "invalid sample rate",
                "device unavailable",
                "no default input",
                "unanticipated host error",
            )
            if any(marker in lowered for marker in device_error_markers):
                self._init_arecord_fallback(str(exc))
            return None

    def _listen_with_arecord(self, max_duration_seconds: float = 10.0) -> Optional[str]:
        if self.model is None:
            print("[STT] arecord can capture from the USB mic, but no transcription engine is installed yet.")
            time.sleep(0.5)
            return None

        duration_seconds = max(1, int(round(max_duration_seconds)))
        sample_rate = int(self._selected_sample_rate or self.sample_rate or 16000)
        temp_wav = ""

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                temp_wav = handle.name

            cmd = [
                "arecord",
                "-D",
                self.arecord_device,
                "-f",
                "S16_LE",
                "-r",
                str(sample_rate),
                "-c",
                "1",
                "-d",
                str(duration_seconds),
                temp_wav,
            ]
            print(
                f"[STT] Recording with arecord "
                f"(device='{self.arecord_device}', sample_rate={sample_rate}, duration={duration_seconds}s)..."
            )
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_seconds + 3, check=False)
            if result.returncode != 0:
                stderr = result.stderr.strip() or result.stdout.strip() or f"arecord exit code {result.returncode}"
                print(f"[STT] arecord failed: {stderr}")
                return None

            return self._transcribe_wav_file(temp_wav)
        except Exception as exc:
            print(f"[STT] arecord capture error: {exc}")
            return None
        finally:
            if temp_wav and os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass

    def _transcribe_wav_file(self, wav_path: str) -> Optional[str]:
        start_time = time.time()
        if self.model is None:
            print("[STT] Faster-Whisper is not available, so arecord fallback cannot transcribe yet.")
            return None

        try:
            segments, _info = self.model.transcribe(
                wav_path,
                beam_size=1,
                language=self.language,
                vad_filter=self.vad_filter,
            )
            text = " ".join(segment.text for segment in segments).strip()
            if text:
                duration = time.time() - start_time
                print(f"[STT] Faster-Whisper ({duration:.2f}s): \"{text}\"")
                return text
            print("[STT] No intelligible speech detected in arecord capture.")
            return None
        except Exception as exc:
            print(f"[STT] Faster-Whisper transcription error: {exc}")
            return None
