"""Instant character thinking fillers to eliminate dead air while LLM and TTS prepare."""

import hashlib
import os
import re
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional


DEFAULT_FILLERS: List[str] = [
    "Hmm, let me consider...",
    "By Gryffindor's sword, let me ponder that...",
    "An intriguing query, traveler!",
    "Aha! Let me ponder that...",
    "Let me consult the castle archives...",
    "A curious thought, wanderer...",
    "Hold, let me delve into my memories...",
    "Ah, let me reflect upon that...",
]


class FillerManager:
    """Pre-caches and instantly serves character audio fillers for the THINKING state."""

    def __init__(
        self,
        config: Dict[str, Any],
        tts: Any,
        lipsync_engine: Any = None,
    ):
        self.config = config
        self.tts = tts
        self.lipsync_engine = lipsync_engine

        tts_cfg = config.get("tts", {})
        configured_fillers = tts_cfg.get("fillers")
        if configured_fillers and isinstance(configured_fillers, list):
            self.filler_phrases = [str(f).strip() for f in configured_fillers if str(f).strip()]
        else:
            self.filler_phrases = list(DEFAULT_FILLERS)

        base_cache_dir = tts_cfg.get(
            "cache_dir",
            os.path.join(config.get("hardware", {}).get("cache_dir", "/tmp"), "tts"),
        )
        self.cache_dir = os.path.abspath(os.path.join(base_cache_dir, "fillers"))
        os.makedirs(self.cache_dir, exist_ok=True)

        self._cache: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = list(self.filler_phrases)
        self._index = 0
        self._lock = threading.Lock()
        self._warmed = False

    def warmup(self) -> None:
        """Pre-synthesize all filler audio clips and lipsync frames off the main thread."""
        with self._lock:
            for phrase in self.filler_phrases:
                if phrase in self._cache:
                    continue
                prepared = self._prepare_single_filler(phrase)
                if prepared:
                    self._cache[phrase] = prepared
            self._warmed = True
            print(f"[FillerManager] Warmed up {len(self._cache)} instant thinking fillers.")

    def _prepare_single_filler(self, phrase: str) -> Optional[Dict[str, Any]]:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", phrase.lower()).strip("_")[:20]
        h = hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:8]
        wav_path = os.path.join(self.cache_dir, f"filler_{slug}_{h}.wav")

        if not self._is_valid_wav(wav_path):
            try:
                output, _ = self.tts.synthesize_to_file(phrase, wav_path)
                if output and os.path.abspath(output) != os.path.abspath(wav_path):
                    import shutil
                    shutil.copyfile(output, wav_path)
            except Exception as exc:
                print(f"[FillerManager] TTS synthesis failed for '{phrase}': {exc}; creating synthetic tone.")
                self._write_fallback_wav(wav_path)

        if not self._is_valid_wav(wav_path):
            self._write_fallback_wav(wav_path)

        duration = self._get_wav_duration(wav_path)
        frames = []
        if self.lipsync_engine is not None and hasattr(self.lipsync_engine, "analyze_wav"):
            try:
                frames = self.lipsync_engine.analyze_wav(wav_path)
            except Exception as exc:
                print(f"[FillerManager] Lipsync analysis notice: {exc}")
                frames = []

        return {
            "text": phrase,
            "path": wav_path,
            "frames": frames,
            "duration": duration,
        }

    def get_filler(self) -> Dict[str, Any]:
        """Return the next prepared filler item instantly (0ms latency)."""
        with self._lock:
            if not self._cache:
                self.warmup()
            if not self._cache:
                # Emergency fallback if all cache preparation failed
                phrase = self.filler_phrases[0] if self.filler_phrases else "Hmm..."
                emergency_path = os.path.join(self.cache_dir, "emergency_filler.wav")
                self._write_fallback_wav(emergency_path)
                return {
                    "text": phrase,
                    "path": emergency_path,
                    "frames": [],
                    "duration": self._get_wav_duration(emergency_path),
                }

            available = [p for p in self._order if p in self._cache]
            if not available:
                available = list(self._cache.keys())

            selected_phrase = available[self._index % len(available)]
            self._index += 1
            item = self._cache[selected_phrase]
            return {
                "text": item["text"],
                "path": item["path"],
                "frames": list(item["frames"]),
                "duration": item["duration"],
            }

    def play_filler(
        self,
        filler: Dict[str, Any],
        on_viseme: Optional[Callable[[str, float], None]] = None,
        on_subtitle: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
        fps: int = 30,
    ) -> bool:
        """Play a filler audio clip, updating subtitles and lipsync visemes."""
        try:
            import pygame.mixer
            if not pygame.mixer.get_init():
                return False

            sound = pygame.mixer.Sound(filler["path"])
            channel = pygame.mixer.Channel(0)
            channel.play(sound)
            started = time.perf_counter()

            if on_subtitle and filler.get("text"):
                on_subtitle(filler["text"])

            frames = filler.get("frames", [])
            while channel.get_busy():
                if stop_event and stop_event.is_set():
                    channel.stop()
                    return False
                if on_viseme and frames:
                    idx = int((time.perf_counter() - started) * fps)
                    if idx < len(frames):
                        frame = frames[idx]
                        if isinstance(frame, dict):
                            on_viseme(frame.get("viseme", "X"), frame.get("amplitude", 0.0))
                        else:
                            on_viseme("O", float(frame))
                time.sleep(0.01)

            if on_viseme:
                on_viseme("X", 0.0)
            return True
        except Exception as exc:
            print(f"[FillerManager] Playback notice: {exc}")
            return False

    @staticmethod
    def _is_valid_wav(wav_path: str) -> bool:
        try:
            if not os.path.isfile(wav_path) or os.path.getsize(wav_path) < 44:
                return False
            with wave.open(wav_path, "rb") as wav_file:
                return wav_file.getnframes() > 0 and wav_file.getframerate() > 0
        except Exception:
            return False

    @staticmethod
    def _get_wav_duration(wav_path: str) -> float:
        try:
            with wave.open(wav_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                return frames / float(rate)
        except Exception:
            return 1.2

    @staticmethod
    def _write_fallback_wav(path: str) -> None:
        """Write a small valid WAV file as a fallback."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        sample_rate = 22050
        num_samples = int(sample_rate * 0.8)  # 800ms
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * num_samples)
