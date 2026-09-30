"""Piper local neural TTS engine driver for Raspberry Pi 5 / Desktop."""
import os
import hashlib
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from typing import Any, Dict, List, Tuple

from tts.base import BaseTTS


class PiperTTS(BaseTTS):
    """Keep a Piper voice in memory, with a standalone executable fallback."""

    def __init__(self, config: Dict[str, Any]):
        tts_cfg = config.get("tts", {})
        self.piper_binary = tts_cfg.get("piper_binary_path", "/mnt/portrait/models/piper/piper")
        self.model_path = tts_cfg.get("model_path", "/mnt/portrait/models/piper/en_US-ryan-medium.onnx")
        self.model_config = tts_cfg.get("model_config_path", f"{self.model_path}.json")
        self.speaker_id = int(tts_cfg.get("speaker_id", 0))
        self.length_scale = float(tts_cfg.get("length_scale", 1.0))
        self.noise_scale = float(tts_cfg.get("noise_scale", 0.667))
        self.noise_w = float(tts_cfg.get("noise_w", 0.8))
        self.runtime = str(tts_cfg.get("runtime", "auto")).lower()
        if self.runtime not in ("auto", "python", "cli"):
            raise ValueError("tts.runtime must be 'auto', 'python', or 'cli'")
        self.synthesis_timeout_seconds = max(1.0, float(tts_cfg.get("synthesis_timeout_seconds", 30.0)))
        self.cache_enabled = bool(tts_cfg.get("cache_enabled", True))
        self.allow_synthetic_fallback = bool(tts_cfg.get("allow_synthetic_fallback", False))
        self.cache_max_entries = max(0, int(tts_cfg.get("cache_max_entries", 128)))
        self.cache_dir = tts_cfg.get(
            "cache_dir",
            os.path.join(config.get("hardware", {}).get("cache_dir", "/tmp"), "tts"),
        )
        self.empty_text_fallback = tts_cfg.get(
            "empty_text_fallback",
            "The castle spirits stole my words. Ask me again, brave visitor!",
        )

        self.last_engine = "uninitialized"
        self.last_error = ""
        self._runtime_bundle_dir = ""
        self._runtime_temp = None
        self._synthesis_lock = threading.Lock()
        self._voice = None
        self._synthesis_config = None
        self._python_unavailable = False
        self._active_process = None
        self._closed = threading.Event()

        # CLI runs in its own runtime directory; resolve arguments before that
        # cwd change so project-relative voice paths continue to work.
        self.model_path = os.path.abspath(os.path.expanduser(self.model_path))
        self.model_config = os.path.abspath(os.path.expanduser(self.model_config))
        self.cache_dir = os.path.abspath(os.path.expanduser(self.cache_dir))

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

            # Archives commonly add one piper/ directory. Avoid recursively
            # scanning /usr/bin and model trees at every app startup.
            candidates.append(os.path.join(root, "piper", "piper"))

        for path in candidates:
            if self._is_executable_file(path):
                self.piper_binary = os.path.abspath(path)
                print(f"[TTS] Located Piper executable: {self.piper_binary}")
                return

        print(
            f"[TTS] No standalone Piper executable found near '{self.piper_binary}'. "
            "The Python runtime will be used if installed."
        )

    def warmup(self, text: str = "") -> None:
        """Optionally prime the persistent voice and a greeting off the UI thread."""
        if self._closed.is_set():
            return
        if text:
            with tempfile.TemporaryDirectory(prefix="hpport-tts-warmup-") as tmpdir:
                self.synthesize_to_file(text, os.path.join(tmpdir, "greeting.wav"))
        else:
            with self._synthesis_lock:
                self._load_python_voice()

    def _load_python_voice(self) -> bool:
        if self._closed.is_set() or self.runtime == "cli" or self._python_unavailable:
            return False
        if self._voice is not None:
            return True
        try:
            from piper import PiperVoice, SynthesisConfig

            self._voice = PiperVoice.load(
                self.model_path,
                config_path=self.model_config if os.path.isfile(self.model_config) else None,
                use_cuda=False,
            )
            self._synthesis_config = SynthesisConfig(
                speaker_id=self.speaker_id,
                length_scale=self.length_scale,
                noise_scale=self.noise_scale,
                noise_w_scale=self.noise_w,
            )
            print("[TTS] Persistent Piper voice ready (Python runtime).")
            return True
        except Exception as exc:
            self._voice = None
            self._python_unavailable = True
            self.last_error = f"Piper Python runtime unavailable: {exc}"
            print(f"[TTS] {self.last_error}")
            return False

    def _run_python(self, text: str, output_wav_path: str, start_time: float) -> Tuple[str, float] | None:
        if not self._load_python_voice() or self._closed.is_set():
            return None
        try:
            with wave.open(output_wav_path, "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file, syn_config=self._synthesis_config)
            if not self._is_valid_wav(output_wav_path):
                raise ValueError("Piper Python runtime produced an empty WAV")
            self.last_engine = "piper_python"
            self.last_error = ""
            duration = self._get_wav_duration(output_wav_path)
            print(f"[TTS] Piper generated speech in {time.monotonic() - start_time:.2f}s (audio: {duration:.2f}s)")
            return output_wav_path, duration
        except Exception as exc:
            self.last_error = f"Piper Python synthesis error: {exc}"
            print(f"[TTS] {self.last_error}")
            # Broken native installations should not retry a model load on every
            # response; the independent executable can still provide speech.
            self._python_unavailable = True
            self._voice = None
            return None

    def synthesize_to_file(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        if self._closed.is_set():
            raise RuntimeError("PiperTTS is closed")
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)
        output_wav_path = os.path.abspath(output_wav_path)
        start_time = time.monotonic()
        text = (text or "").strip()
        if not text:
            self.last_error = "Piper received empty text from the response pipeline"
            text = self.empty_text_fallback
            print(f"[TTS] {self.last_error}; speaking recovery text instead.")

        with self._synthesis_lock:
            if self._closed.is_set():
                raise RuntimeError("PiperTTS is closed")
            self.last_engine = "unknown"
            self.last_error = ""
            if not os.path.exists(self.model_path):
                self.last_error = f"Piper voice model not found at {self.model_path}"
                print(f"[TTS] {self.last_error}")
                return self._create_fallback_audio(output_wav_path, text)
            cached = self._restore_cached_audio(text, output_wav_path, start_time)
            if cached is not None:
                return cached

            result = self._run_python(text, output_wav_path, start_time)
            if result is not None:
                self._cache_audio(text, output_wav_path)
                return result
            if self.runtime == "python":
                return self._create_fallback_audio(output_wav_path, text)

            if self._is_executable_file(self.piper_binary):
                result = self._run_piper(self.piper_binary, text, output_wav_path, start_time)
                if result is not None:
                    self._cache_audio(text, output_wav_path)
                    return result

                if self._should_retry_from_tmp():
                    staged_binary = self._stage_runtime_bundle_to_tmp()
                    if staged_binary:
                        print(f"[TTS] Retrying Piper from temporary runtime bundle: {staged_binary}")
                        result = self._run_piper(staged_binary, text, output_wav_path, start_time)
                        if result is not None:
                            self._cache_audio(text, output_wav_path)
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
        process = None

        try:
            if self._closed.is_set():
                return None
            # Never accept a stale file from an earlier utterance as success.
            if os.path.isfile(output_wav_path):
                os.remove(output_wav_path)
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=os.path.dirname(binary_path) or None,
            )
            self._active_process = process
            if self._closed.is_set():
                process.kill()
            try:
                _stdout, stderr = process.communicate(input=text, timeout=self.synthesis_timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=1.0)
                self.last_error = f"Piper exceeded {self.synthesis_timeout_seconds:g}s synthesis timeout"
                print(f"[TTS] {self.last_error}")
                return None

            if process.returncode == 0 and self._is_valid_wav(output_wav_path):
                duration = self._get_wav_duration(output_wav_path)
                self.last_engine = "piper"
                self.last_error = ""
                synth_time = time.monotonic() - start_time
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
        finally:
            self._active_process = None
            if process is not None:
                if process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=0.5)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass

    @staticmethod
    def _is_valid_wav(wav_path: str) -> bool:
        try:
            with wave.open(wav_path, "rb") as wav_file:
                return (
                    wav_file.getnframes() > 0
                    and wav_file.getframerate() > 0
                    and len(wav_file.readframes(1)) == wav_file.getnchannels() * wav_file.getsampwidth()
                )
        except (OSError, EOFError, wave.Error):
            return False

    def _cache_path(self, text: str) -> str:
        def identity(path: str) -> str:
            try:
                stat = os.stat(path)
                return f"{path}:{stat.st_size}:{stat.st_mtime_ns}"
            except OSError:
                return path

        cache_key = "|".join(
            (
                "piper-v2",
                identity(self.model_path),
                identity(self.model_config),
                str(self.speaker_id),
                str(self.length_scale),
                str(self.noise_scale),
                str(self.noise_w),
                text,
            )
        )
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.wav")

    def _restore_cached_audio(
        self, text: str, output_wav_path: str, start_time: float
    ) -> Tuple[str, float] | None:
        if not self.cache_enabled or self.cache_max_entries == 0:
            return None
        cache_path = self._cache_path(text)
        if not self._is_valid_wav(cache_path):
            return None
        try:
            if os.path.abspath(cache_path) != os.path.abspath(output_wav_path):
                shutil.copyfile(cache_path, output_wav_path)
        except OSError as exc:
            print(f"[TTS] Audio cache read notice: {exc}")
            return None
        try:
            os.utime(cache_path, None)
        except OSError:
            pass
        duration = self._get_wav_duration(output_wav_path)
        self.last_engine = "piper_cache"
        print(f"[TTS] Restored cached Piper audio in {time.monotonic() - start_time:.2f}s")
        return output_wav_path, duration

    def _cache_audio(self, text: str, wav_path: str) -> None:
        if not self.cache_enabled or self.cache_max_entries == 0 or not self._is_valid_wav(wav_path):
            return
        temporary_path = ""
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, suffix=".tmp", delete=False) as temporary:
                temporary_path = temporary.name
            shutil.copyfile(wav_path, temporary_path)
            os.replace(temporary_path, self._cache_path(text))
            self._prune_cache()
        except OSError as exc:
            print(f"[TTS] Audio cache notice: {exc}")
        finally:
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass

    def _prune_cache(self) -> None:
        # Only prune files owned by this cache, never unrelated user WAV files.
        entries = []
        with os.scandir(self.cache_dir) as files:
            for entry in files:
                stem, extension = os.path.splitext(entry.name)
                if extension == ".wav" and len(stem) == 64 and all(c in "0123456789abcdef" for c in stem):
                    if entry.is_file(follow_symlinks=False):
                        entries.append((entry.stat().st_mtime_ns, entry.path))
        entries.sort()
        for _, path in entries[:max(0, len(entries) - self.cache_max_entries)]:
            try:
                os.remove(path)
            except OSError:
                pass

    def _should_retry_from_tmp(self) -> bool:
        lowered = self.last_error.lower()
        return "permission denied" in lowered or "operation not permitted" in lowered or "text file busy" in lowered

    def _stage_runtime_bundle_to_tmp(self) -> str:
        source_binary = self.piper_binary
        source_bundle = os.path.dirname(source_binary)
        if self._runtime_bundle_dir:
            return os.path.join(self._runtime_bundle_dir, os.path.basename(source_binary))

        # Only relocate self-contained bundles. Copying all of /usr/bin or a
        # model directory to /tmp can fill a Pi's disk or memory filesystem.
        if not os.path.isdir(os.path.join(source_bundle, "espeak-ng-data")):
            return ""

        try:
            self._runtime_temp = tempfile.TemporaryDirectory(prefix="hpport-piper-")
            target_bundle = self._runtime_temp.name
            for name in os.listdir(source_bundle):
                source = os.path.join(source_bundle, name)
                target = os.path.join(target_bundle, name)
                if name == "espeak-ng-data":
                    shutil.copytree(source, target)
                elif name == os.path.basename(source_binary) or ".so" in name or name.endswith((".dll", ".dylib")):
                    if os.path.isfile(source):
                        shutil.copy2(source, target)
            staged_binary = os.path.join(target_bundle, os.path.basename(source_binary))
            if os.path.exists(staged_binary):
                os.chmod(staged_binary, 0o755)
                self._runtime_bundle_dir = target_bundle
                return staged_binary
        except Exception as exc:
            self.last_error = f"Failed to stage Piper runtime bundle: {exc}"
            print(f"[TTS] {self.last_error}")

        return ""

    def close(self) -> None:
        """Stop a CLI worker and release owned resources without blocking shutdown."""
        self._closed.set()
        process = self._active_process
        if process is not None:
            try:
                process.kill()
            except OSError:
                pass
        if self._synthesis_lock.acquire(timeout=0.5):
            try:
                self._voice = None
                if self._runtime_temp is not None:
                    self._runtime_temp.cleanup()
                    self._runtime_temp = None
                    self._runtime_bundle_dir = ""
            finally:
                self._synthesis_lock.release()

    def _get_wav_duration(self, wav_path: str) -> float:
        try:
            with wave.open(wav_path, "r") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                return frames / float(rate)
        except Exception:
            return 2.0

    def _create_fallback_audio(self, wav_path: str, text: str) -> Tuple[str, float]:
        if not self.allow_synthetic_fallback:
            self.last_engine = "unavailable"
            raise RuntimeError(self.last_error or "Piper is unavailable; install its runtime and voice model")
        from tts.mock_tts import MockTTS

        self.last_engine = "mock_fallback"
        print("[TTS] Using synthetic fallback audio. This produces a humming tone, not spoken words.")
        mock = MockTTS()
        return mock.synthesize_to_file(text, wav_path)
