"""Local STT driver using Faster-Whisper and SpeechRecognition on Raspberry Pi 5 / Desktop."""

import array
import io
import math
import os
import re
import select
import shutil
import subprocess
import time
import wave
from collections import deque
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
        self.model_download_root = os.path.expanduser(str(stt_cfg.get(
            "model_download_root",
            os.path.join(config.get("hardware", {}).get("models_dir", "/mnt/portrait/models"), "stt"),
        )))
        self.local_files_only = bool(stt_cfg.get("local_files_only", False))
        self.vad_filter = stt_cfg.get("vad_filter", True)
        self.energy_threshold = int(stt_cfg.get("energy_threshold", 300))
        self.dynamic_energy_threshold = bool(stt_cfg.get("dynamic_energy_threshold", True))
        self.ambient_calibration_seconds = float(stt_cfg.get("ambient_calibration_seconds", 0.3))
        self.pause_threshold = max(0.1, float(stt_cfg.get("pause_threshold", 0.5)))
        self.non_speaking_duration = min(
            self.pause_threshold, max(0.0, float(stt_cfg.get("non_speaking_duration", 0.2)))
        )
        self.phrase_threshold = max(0.0, float(stt_cfg.get("phrase_threshold", 0.15)))
        self.cpu_threads = max(1, int(stt_cfg.get("cpu_threads", 2)))
        self.allow_online_fallback = bool(stt_cfg.get("allow_online_fallback", False))
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
            self.recognizer.pause_threshold = self.pause_threshold
            self.recognizer.non_speaking_duration = self.non_speaking_duration
            self.recognizer.phrase_threshold = self.phrase_threshold
            self.recognizer.operation_timeout = 5.0

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
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                num_workers=1,
                download_root=self.model_download_root,
                local_files_only=self.local_files_only,
            )
            print("[STT] Faster-Whisper model ready.")
        except Exception as exc:
            print(
                f"[STT] Faster-whisper model load notice ({exc}). "
                "Install it in this Python environment to enable transcription."
            )
            self.model = None

    def listen_and_transcribe(self, timeout_seconds: float = 2.0, max_duration_seconds: float = 6.0) -> Optional[str]:
        """Record spoken audio from microphone and transcribe to text."""
        if self._use_arecord_fallback:
            return self._listen_with_arecord(
                timeout_seconds=timeout_seconds,
                max_duration_seconds=max_duration_seconds,
            )

        if not self._mic_available or not self.recognizer or not self.microphone:
            print("[STT] Microphone not available. Simulating brief listening wait (or press 'T' in window)...")
            time.sleep(1.2)
            return None

        import speech_recognition as sr  # type: ignore

        print(
            f"[STT] Listening for user speech "
            f"(device={self._selected_device_index}, timeout={timeout_seconds}s, max={max_duration_seconds}s)..."
        )
        start_time = time.monotonic()

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

            record_duration = time.monotonic() - start_time
            print(f"[STT] Audio captured in {record_duration:.2f}s. Transcribing...")

            if self.model is not None:
                wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
                wav_file = io.BytesIO(wav_bytes)
                # An empty local result means silence/unclear speech, not a reason
                # to make a second, slower network transcription request.
                return self._transcribe_audio(wav_file)

            if not self.allow_online_fallback:
                print("[STT] No local transcription engine available; online fallback is disabled.")
                return None

            text = self.recognizer.recognize_google(audio_data)
            duration = time.monotonic() - start_time
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

    def _listen_with_arecord(
        self, timeout_seconds: float = 2.0, max_duration_seconds: float = 6.0
    ) -> Optional[str]:
        if self.model is None:
            print("[STT] arecord can capture from the USB mic, but no transcription engine is installed yet.")
            time.sleep(0.5)
            return None

        sample_rate = int(self._selected_sample_rate or self.sample_rate or 16000)
        # 50ms chunks of 16-bit mono PCM = sample_rate * 2 bytes * 0.05
        chunk_samples = max(1, int(sample_rate * 0.05))
        chunk_bytes = chunk_samples * 2
        threshold = max(180.0, float(self.energy_threshold) * 0.75)
        consecutive_silence_threshold = max(1, math.ceil(self.pause_threshold / 0.05))

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
            "-t",
            "raw",
            "-q",
        ]

        captured_chunks: List[bytes] = []
        # Preserve the onset without sending the whole initial silence window
        # through Whisper. This also bounds memory when nobody is speaking.
        pre_roll = deque(maxlen=max(1, math.ceil(self.non_speaking_duration / 0.05)))
        speech_started = False
        consecutive_silence = 0
        voiced_chunks = 0
        start_time = time.monotonic()
        max_deadline = None
        initial_timeout_deadline = start_time + timeout_seconds

        print(
            f"[STT] Streaming arecord with VAD "
            f"(device='{self.arecord_device}', sample_rate={sample_rate}, threshold={threshold:.0f})..."
        )

        process = None
        pending = bytearray()
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )

            while True:
                now = time.monotonic()
                if max_deadline is not None and now >= max_deadline:
                    print(f"[STT] arecord reached maximum duration ({max_duration_seconds:.1f}s).")
                    break

                if not speech_started and now > initial_timeout_deadline:
                    print(f"[STT] arecord initial silence timeout ({timeout_seconds:.1f}s).")
                    break

                if process.stdout is None:
                    break

                deadline = max_deadline if speech_started else initial_timeout_deadline
                ready, _, _ = select.select([process.stdout], [], [], max(0.0, min(0.1, deadline - now)))
                if not ready:
                    continue
                # Unbuffered pipes may return less than requested. Gather one
                # complete 50 ms block, while still checking capture deadlines.
                raw_data = os.read(process.stdout.fileno(), chunk_bytes - len(pending))
                if not raw_data:
                    break
                pending.extend(raw_data)
                if len(pending) < chunk_bytes:
                    continue
                raw_data = bytes(pending)
                pending.clear()

                # Compute RMS energy of chunk
                samples = array.array("h", raw_data)
                if len(samples) > 0:
                    sum_sq = sum(s * s for s in samples)
                    rms = math.sqrt(sum_sq / len(samples))
                else:
                    rms = 0.0

                if rms >= threshold:
                    if not speech_started:
                        speech_started = True
                        max_deadline = time.monotonic() + max_duration_seconds
                        captured_chunks.extend(pre_roll)
                        print(f"[STT] Voice activity detected (RMS: {rms:.1f})")
                    voiced_chunks += 1
                    consecutive_silence = 0
                else:
                    if speech_started:
                        consecutive_silence += 1
                        if consecutive_silence >= consecutive_silence_threshold:
                            if voiced_chunks * 0.05 < self.phrase_threshold:
                                # Discard isolated clicks; keep listening within
                                # the original wait-for-speech window.
                                speech_started = False
                                max_deadline = None
                                voiced_chunks = 0
                                consecutive_silence = 0
                                captured_chunks.clear()
                                pre_roll.clear()
                                continue
                            print(f"[STT] End of speech detected ({consecutive_silence * 50}ms silence).")
                            break

                if speech_started:
                    captured_chunks.append(raw_data)
                else:
                    pre_roll.append(raw_data)

        except Exception as exc:
            print(f"[STT] arecord streaming capture error: {exc}")
        finally:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=0.3)
                except Exception:
                    try:
                        process.kill()
                        process.wait(timeout=0.3)
                    except Exception:
                        pass
                if process.stdout is not None:
                    process.stdout.close()

        if not speech_started or not captured_chunks or voiced_chunks * 0.05 < self.phrase_threshold:
            print("[STT] arecord: No speech detected in capture window.")
            return None

        total_audio_sec = sum(map(len, captured_chunks)) / (sample_rate * 2.0)
        print(f"[STT] Captured {total_audio_sec:.2f}s of speech. Transcribing...")

        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b"".join(captured_chunks))

            wav_buffer.seek(0)
            return self._transcribe_audio(wav_buffer)
        except Exception as exc:
            print(f"[STT] arecord WAV processing error: {exc}")
            return None

    def _transcribe_audio(self, audio: Any) -> Optional[str]:
        """Decode one short utterance without expensive sampling retries."""
        start_time = time.monotonic()
        if self.model is None:
            print("[STT] Faster-Whisper is not available.")
            return None

        try:
            segments, _info = self.model.transcribe(
                audio,
                beam_size=1,
                language=self.language,
                vad_filter=self.vad_filter,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text for segment in segments).strip()
            if text:
                duration = time.monotonic() - start_time
                print(f"[STT] Faster-Whisper ({duration:.2f}s): \"{text}\"")
                return text
            print("[STT] No intelligible speech detected.")
            return None
        except Exception as exc:
            print(f"[STT] Faster-Whisper transcription error: {exc}")
            return None
