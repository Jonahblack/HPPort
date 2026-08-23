"""Piper local neural TTS engine driver for Raspberry Pi 5 / Desktop."""
import os
import shutil
import subprocess
import time
import wave
from typing import Any, Dict, List, Tuple

from tts.base import BaseTTS


class PiperTTS(BaseTTS):
    """Execute Piper to generate spoken WAV output and expose fallback diagnostics."""

    def __init__(self, config: Dict[str, Any]):
        tts_cfg = config.get("tts", {})
        self.piper_binary = tts_cfg.get("piper_binary_path", "/mnt/portrait/models/piper/piper")
        self.model_path = tts_cfg.get("model_path", "/mnt/portrait/models/piper/en_US-ryan-high.onnx")
        self.model_config = tts_cfg.get("model_config_path", "/mnt/portrait/models/piper/en_US-ryan-high.onnx.json")
        self.speaker_id = int(tts_cfg.get("speaker_id", 0))
        self.length_scale = float(tts_cfg.get("length_scale", 1.0))
        self.noise_scale = float(tts_cfg.get("noise_scale", 0.667))
        self.noise_w = float(tts_cfg.get("noise_w", 0.8))

        self.last_engine = "uninitialized"
        self.last_error = ""
        self._runtime_bundle_dir = ""

        self._find_piper()

    @staticmethod
    def _is_executable_file(path: str) -> bool:
        return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)

    def _search_roots(self) -> List[str]:
        roots = []
        configured_dir = os.path.dirname(os.path.abspath(self.piper_binary))
        model_dir = os.path.dirname(os.path.abspath(self.model_path))
        roots.extend([configured_dir, model_dir, os.path.expanduser("~/piper"), "/usr/local/bin", "/usr/bin"])

        seen = set()
        unique_roots = []
        for root in roots:
            if root and root not in seen and os.path.isdir(root):
                seen.add(root)
                unique_roots.append(root)
        return unique_roots

    def _find_piper(self) -> None:
        """Find Piper executable across standard and extracted archive locations."""
        candidates = [
            self.piper_binary,
            os.path.join(self.piper_binary, "piper") if os.path.isdir(self.piper_binary) else None,
            shutil.which("piper"),
            os.path.expanduser("~/piper/piper"),
            "./models/piper/piper",
            "/usr/local/bin/piper",
            "/usr/bin/piper",
        ]

        for root in self._search_roots():
            direct = os.path.join(root, "piper")
            if direct not in candidates:
                candidates.append(direct)

            try:
                for current_root, _dirs, files in os.walk(root):
                    if "piper" in files:
                        candidates.append(os.path.join(current_root, "piper"))
            except Exception:
                continue

        for path in candidates:
            if self._is_executable_file(path):
                self.piper_binary = path
                print(f"[TTS] Located Piper executable: {self.piper_binary}")
                return

        print(
            f"[TTS] Notice: Piper executable not found near '{self.piper_binary}'. "
            "If you hear a humming tone, the app is using the synthetic fallback instead of real speech."
        )

    def synthesize_to_file(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)
        start_time = time.time()
        self.last_engine = "unknown"
        self.last_error = ""

        if not os.path.exists(self.model_path):
            self.last_error = f"Piper voice model not found at {self.model_path}"
            print(f"[TTS] {self.last_error}")
            return self._create_fallback_audio(output_wav_path, text)

        if self._is_executable_file(self.piper_binary):
            result = self._run_piper(self.piper_binary, text, output_wav_path, start_time)
            if result is not None:
                return result

            if self._should_retry_from_tmp():
                staged_binary = self._stage_runtime_bundle_to_tmp()
                if staged_binary:
                    print(f"[TTS] Retrying Piper from temporary runtime bundle: {staged_binary}")
                    result = self._run_piper(staged_binary, text, output_wav_path, start_time)
                    if result is not None:
                        return result
        else:
            self.last_error = f"Piper executable not found at {self.piper_binary}"
            print(f"[TTS] {self.last_error}")

        return self._create_fallback_audio(output_wav_path, text)

    def _build_cmd(self, binary_path: str, output_wav_path: str) -> List[str]:
        cmd = [
            binary_path,
            "--model",
            self.model_path,
            "--output_file",
            output_wav_path,
            "--speaker",
            str(self.speaker_id),
            "--length_scale",
            str(self.length_scale),
            "--noise_scale",
            str(self.noise_scale),
            "--noise_w",
            str(self.noise_w),
        ]
        if os.path.exists(self.model_config):
            cmd.extend(["--config", self.model_config])
        return cmd

    def _run_piper(self, binary_path: str, text: str, output_wav_path: str, start_time: float) -> Tuple[str, float] | None:
        cmd = self._build_cmd(binary_path, output_wav_path)

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(binary_path) or None,
            )
            _stdout, stderr = process.communicate(input=text)

            if process.returncode == 0 and os.path.exists(output_wav_path):
                duration = self._get_wav_duration(output_wav_path)
                self.last_engine = "piper"
                synth_time = time.time() - start_time
                print(
                    f"[TTS] Piper generated '{output_wav_path}' in {synth_time:.2f}s "
                    f"(audio duration: {duration:.2f}s)"
                )
                return output_wav_path, duration

            self.last_error = stderr.strip() or f"Piper exited with code {process.returncode}"
            print(f"[TTS] Piper failed: {self.last_error}")
            return None
        except OSError as exc:
            self.last_error = f"Piper execution error: {exc}"
            print(f"[TTS] {self.last_error}")
            return None
        except Exception as exc:
            self.last_error = f"Piper execution error: {exc}"
            print(f"[TTS] {self.last_error}")
            return None

    def _should_retry_from_tmp(self) -> bool:
        lowered = self.last_error.lower()
        return "permission denied" in lowered or "operation not permitted" in lowered or "text file busy" in lowered

    def _stage_runtime_bundle_to_tmp(self) -> str:
        source_binary = self.piper_binary
        source_bundle = os.path.dirname(source_binary)
        bundle_name = os.path.basename(source_bundle.rstrip(os.sep)) or "piper_bundle"
        runtime_root = os.path.join("/tmp", "hpport_piper_runtime")
        target_bundle = os.path.join(runtime_root, bundle_name)

        try:
            os.makedirs(runtime_root, exist_ok=True)
            shutil.copytree(source_bundle, target_bundle, dirs_exist_ok=True)
            staged_binary = os.path.join(target_bundle, os.path.basename(source_binary))
            if os.path.exists(staged_binary):
                os.chmod(staged_binary, 0o755)
                self._runtime_bundle_dir = target_bundle
                return staged_binary
        except Exception as exc:
            self.last_error = f"Failed to stage Piper runtime bundle: {exc}"
            print(f"[TTS] {self.last_error}")

        return ""

    def _get_wav_duration(self, wav_path: str) -> float:
        try:
            with wave.open(wav_path, "r") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                return frames / float(rate)
        except Exception:
            return 2.0

    def _create_fallback_audio(self, wav_path: str, text: str) -> Tuple[str, float]:
        from tts.mock_tts import MockTTS

        self.last_engine = "mock_fallback"
        print("[TTS] Using synthetic fallback audio. This produces a humming tone, not spoken words.")
        mock = MockTTS()
        return mock.synthesize_to_file(text, wav_path)
