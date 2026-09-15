"""Animation helpers: Preston-Blair viseme lip-sync engine, eased biological blinking, and micro-saccades."""

import math
import os
import random
import time
import wave
from typing import List, Tuple, Dict, Any, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# Preston Blair Viseme Definitions:
# 'A': Closed lips (M, B, P, or quiet pauses)
# 'B': Slightly parted consonants (K, S, T, D, N, Z)
# 'C': Open mouth vowels (EH, AE, AY)
# 'D': Wide open vowels (AA, AO, AH)
# 'E': Rounded vowels (ER, OW, O)
# 'F': Puckered lips (UW, W, OO)
# 'G': Labiodental (upper teeth on lower lip: F, V)
# 'H': Tongue/teeth articulated (L, TH)
# 'X': Neutral / Rest position
VISEME_NAMES = ("A", "B", "C", "D", "E", "F", "G", "H", "X")


class SaccadeController:
    """Simulates physiological ocular micro-saccades (rapid fixation shifts)."""

    def __init__(
        self,
        min_interval: float = 1.2,
        max_interval: float = 3.0,
        max_jitter_px: float = 2.0,
    ):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.max_jitter_px = max_jitter_px

        self.current_offset_x = 0.0
        self.current_offset_y = 0.0
        self.target_offset_x = 0.0
        self.target_offset_y = 0.0

        self.next_saccade_time = time.time() + random.uniform(self.min_interval, self.max_interval)
        self.saccade_end_time = 0.0

    def update(self) -> Tuple[float, float]:
        """Update and return (jitter_x, jitter_y) in pixels."""
        now = time.time()

        if now >= self.next_saccade_time:
            angle = random.uniform(0.0, math.tau)
            dist = random.uniform(0.5, self.max_jitter_px)
            self.target_offset_x = math.cos(angle) * dist
            self.target_offset_y = math.sin(angle) * dist * 0.6
            self.saccade_end_time = now + random.uniform(0.08, 0.18)
            self.next_saccade_time = now + random.uniform(self.min_interval, self.max_interval)

        if now >= self.saccade_end_time:
            self.target_offset_x = 0.0
            self.target_offset_y = 0.0

        lerp_speed = 0.35
        self.current_offset_x += (self.target_offset_x - self.current_offset_x) * lerp_speed
        self.current_offset_y += (self.target_offset_y - self.current_offset_y) * lerp_speed

        return (self.current_offset_x, self.current_offset_y)


class BlinkController:
    """Randomized biological eye-blink controller with asymmetric easing and double blinks."""

    def __init__(
        self,
        min_interval_sec: float = 2.2,
        max_interval_sec: float = 5.5,
        blink_duration_ms: int = 180,
    ):
        self.min_interval = min_interval_sec
        self.max_interval = max_interval_sec
        self.blink_duration_sec = max(0.12, blink_duration_ms / 1000.0)

        self.next_blink_time = time.time() + random.uniform(self.min_interval, self.max_interval)
        self.is_blinking = False
        self.blink_start_time = 0.0
        self.closure_progress = 0.0
        self.current_stage = "open"

    def update(self) -> bool:
        """Call each frame. Returns True if eyes are not fully open."""
        now = time.time()

        if not self.is_blinking:
            self.closure_progress = 0.0
            self.current_stage = "open"
            if now >= self.next_blink_time:
                self.is_blinking = True
                self.blink_start_time = now
        else:
            elapsed = now - self.blink_start_time
            total = self.blink_duration_sec

            if elapsed >= total:
                self.is_blinking = False
                self.closure_progress = 0.0
                self.current_stage = "open"
                if random.random() < 0.18:
                    self.next_blink_time = now + random.uniform(0.12, 0.25)
                else:
                    self.next_blink_time = now + random.uniform(self.min_interval, self.max_interval)
            else:
                norm = elapsed / total
                if norm < 0.35:
                    t = norm / 0.35
                    self.closure_progress = t * t
                elif norm < 0.55:
                    self.closure_progress = 1.0
                else:
                    t = (norm - 0.55) / 0.45
                    self.closure_progress = 1.0 - math.sin(t * (math.pi / 2))

                if self.closure_progress < 0.20:
                    self.current_stage = "open"
                elif self.closure_progress < 0.80:
                    self.current_stage = "half"
                else:
                    self.current_stage = "closed"

        return self.closure_progress > 0.05

    def get_stage(self) -> str:
        """Returns 'open', 'half', or 'closed'."""
        return self.current_stage

    def get_progress(self) -> float:
        """Returns 0.0 (open) to 1.0 (closed)."""
        return self.closure_progress


class LipSyncEngine:
    """Computes phonetic Preston-Blair visemes and RMS amplitudes for realistic speech animation."""

    def __init__(
        self,
        threshold_mouth_2: float = 0.15,
        threshold_mouth_3: float = 0.45,
        crossfade_ms: int = 35,
    ):
        self.threshold_mouth_2 = threshold_mouth_2
        self.threshold_mouth_3 = threshold_mouth_3
        self.crossfade_duration = crossfade_ms / 1000.0

        self.current_viseme = "X"
        self.previous_viseme = "X"
        self.viseme_change_time = time.time()

    def analyze_wav(self, wav_path: str, fps: int = 60) -> List[Dict[str, Any]]:
        """Convert a WAV file into a list of frame animation dicts containing:
        - 'amplitude': normalized RMS (0.0 to 1.0)
        - 'viseme': Preston-Blair viseme ('A' through 'H', 'X')
        - 'mouth_index': legacy 1, 2, 3 shape index
        """
        rhubarb_json_path = os.path.splitext(wav_path)[0] + ".json"
        rhubarb_cues = self._load_rhubarb_json(rhubarb_json_path)

        try:
            with wave.open(wav_path, "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                raw_bytes = wf.readframes(nframes)

            if HAS_NUMPY:
                dtype = np.int16 if sampwidth == 2 else np.int8
                samples = np.frombuffer(raw_bytes, dtype=dtype).astype(np.float32)
                if channels > 1:
                    samples = samples[::channels]
            else:
                import array
                typecode = "h" if sampwidth == 2 else "b"
                arr = array.array(typecode)
                arr.frombytes(raw_bytes)
                samples = [float(x) for x in (arr[::channels] if channels > 1 else arr)]

            samples_per_frame = max(1, int(framerate / fps))
            total_samples = len(samples)
            num_frames = int(math.ceil(total_samples / samples_per_frame))

            frames_data = []
            max_rms = 1.0

            rms_list = []
            zcr_list = []

            for i in range(num_frames):
                start = i * samples_per_frame
                end = min(total_samples, start + samples_per_frame)
                chunk = samples[start:end]

                if len(chunk) > 0:
                    if HAS_NUMPY:
                        chunk_np = np.asarray(chunk)
                        rms = float(np.sqrt(np.mean(chunk_np**2)))
                        zero_crossings = int(np.sum(np.diff(chunk_np > 0) != 0))
                        zcr = zero_crossings / len(chunk_np)
                    else:
                        sum_sq = sum(x * x for x in chunk)
                        rms = math.sqrt(sum_sq / len(chunk))
                        zc = 0
                        for idx in range(1, len(chunk)):
                            if (chunk[idx] > 0) != (chunk[idx - 1] > 0):
                                zc += 1
                        zcr = zc / len(chunk)

                    rms_list.append(rms)
                    zcr_list.append(zcr)
                    if rms > max_rms:
                        max_rms = rms
                else:
                    rms_list.append(0.0)
                    zcr_list.append(0.0)

            for i in range(num_frames):
                raw_rms = rms_list[i]
                zcr = zcr_list[i]
                norm_rms = min(1.0, raw_rms / (max_rms * 0.82)) if max_rms > 0 else 0.0
                frame_time_sec = i / float(fps)

                if rhubarb_cues:
                    viseme = self._get_viseme_from_cues(rhubarb_cues, frame_time_sec)
                else:
                    viseme = self._estimate_viseme(norm_rms, zcr)

                mouth_index = self.viseme_to_legacy_index(viseme)

                frames_data.append({
                    "amplitude": round(norm_rms, 3),
                    "viseme": viseme,
                    "mouth_index": mouth_index,
                })

            return frames_data

        except Exception as e:
            print(f"[LipSync] Notice: Could not analyze WAV {wav_path} ({e}). Generating synthetic viseme stream.")
            return [
                {
                    "amplitude": round(0.3 * (1 + math.sin(i * 0.4)), 3),
                    "viseme": ("B" if (i // 4) % 2 == 0 else "C"),
                    "mouth_index": (2 if (i // 4) % 2 == 0 else 3),
                }
                for i in range(fps * 3)
            ]

    def _estimate_viseme(self, norm_rms: float, zcr: float) -> str:
        """Classify audio slice into Preston-Blair viseme using energy and spectral cues."""
        if norm_rms < 0.06:
            return "X"
        elif norm_rms < 0.16:
            return "A" if zcr < 0.08 else "B"
        elif norm_rms < 0.42:
            if zcr > 0.16:
                return "G"
            elif zcr > 0.11:
                return "B"
            elif zcr < 0.05:
                return "E"
            else:
                return "C"
        else:
            if zcr > 0.14:
                return "H"
            elif zcr < 0.06:
                return "F" if norm_rms < 0.65 else "E"
            else:
                return "D"

    def viseme_to_legacy_index(self, viseme: str) -> int:
        """Map Preston-Blair viseme to legacy 3-tier sprite index (1=closed, 2=mid, 3=wide)."""
        if viseme in ("X", "A"):
            return 1
        elif viseme in ("B", "E", "F", "G", "H"):
            return 2
        elif viseme in ("C", "D"):
            return 3
        return 1

    def get_mouth_shape_index(self, amplitude: float) -> int:
        """Preserve backwards compatibility for direct RMS amplitude queries."""
        if amplitude >= self.threshold_mouth_3:
            return 3
        elif amplitude >= self.threshold_mouth_2:
            return 2
        return 1

    def set_active_viseme(self, viseme: str) -> None:
        """Update active viseme and track transition time for smooth alpha cross-fading."""
        viseme = viseme.upper()
        if viseme != self.current_viseme:
            self.previous_viseme = self.current_viseme
            self.current_viseme = viseme
            self.viseme_change_time = time.time()

    def get_crossfade_alpha(self) -> float:
        """Returns 0.0 to 1.0 progress of the transition between previous and current viseme."""
        if self.crossfade_duration <= 0:
            return 1.0
        elapsed = time.time() - self.viseme_change_time
        return min(1.0, max(0.0, elapsed / self.crossfade_duration))

    def _load_rhubarb_json(self, path: str) -> List[Dict[str, Any]]:
        """Load optional Rhubarb Lip Sync JSON export."""
        if not os.path.exists(path):
            return []
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("mouthCues", [])
        except Exception:
            return []

    def _get_viseme_from_cues(self, cues: List[Dict[str, Any]], time_sec: float) -> str:
        """Search cues for active viseme at given timestamp."""
        for cue in cues:
            if cue.get("start", 0.0) <= time_sec <= cue.get("end", 0.0):
                return str(cue.get("value", "X")).upper()
        return "X"
