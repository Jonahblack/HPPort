"""Animation helpers: Preston-Blair viseme lip-sync engine, eased biological blinking, and micro-saccades."""

import math
import os
import random
import time
import wave
from typing import List, Tuple, Dict, Any, Optional, Callable

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

        self._last_update = time.monotonic()
        self.next_saccade_time = self._last_update + random.uniform(self.min_interval, self.max_interval)
        self.saccade_end_time = 0.0

    def update(self) -> Tuple[float, float]:
        """Update and return (jitter_x, jitter_y) in pixels (strictly 1-2px bounded)."""
        now = time.monotonic()
        delta = min(0.1, max(0.0, now - self._last_update))
        self._last_update = now

        if now >= self.next_saccade_time:
            angle = random.uniform(0.0, math.tau)
            dist = random.uniform(0.8, self.max_jitter_px)
            self.target_offset_x = math.cos(angle) * dist
            self.target_offset_y = math.sin(angle) * dist * 0.6
            self.saccade_end_time = now + random.uniform(0.08, 0.18)
            self.next_saccade_time = now + random.uniform(self.min_interval, self.max_interval)

        if now >= self.saccade_end_time:
            self.target_offset_x = 0.0
            self.target_offset_y = 0.0

        lerp_speed = 1.0 - math.exp(-26.0 * delta)
        self.current_offset_x += (self.target_offset_x - self.current_offset_x) * lerp_speed
        self.current_offset_y += (self.target_offset_y - self.current_offset_y) * lerp_speed

        return (self.current_offset_x, self.current_offset_y)


class BlinkController:
    """Randomized biological eye-blink controller with asymmetric easing and double blinks."""

    def __init__(
        self,
        min_interval_sec: float = 2.5,
        max_interval_sec: float = 5.5,
        blink_duration_ms: int = 180,
    ):
        self.min_interval = min_interval_sec
        self.max_interval = max_interval_sec
        self.blink_duration_sec = max(0.10, blink_duration_ms / 1000.0)

        self.next_blink_time = time.monotonic() + random.uniform(self.min_interval, self.max_interval)
        self.is_blinking = False
        self.blink_start_time = 0.0
        self.closure_progress = 0.0
        self.current_stage = "open"

    def update(self) -> bool:
        """Call each frame. Returns True if eyes are not fully open."""
        now = time.monotonic()

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
                # Asymmetric biological easing: rapid ease-in closing (35%), brief hold (15%), gentle ease-out opening (50%)
                if norm < 0.35:
                    t = norm / 0.35
                    self.closure_progress = t * t
                elif norm < 0.50:
                    self.closure_progress = 1.0
                else:
                    t = (norm - 0.50) / 0.50
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


class BreathingController:
    """Simulates physiological chest breathing drift with sinusoidal vertical oscillation (2-3px).

    Follows the Living Portrait principle from AGENTS.md:
    Wilhelm's chest breathes with a natural sinusoidal vertical drift of 2-3 pixels.
    """

    def __init__(
        self,
        amplitude_px: float = 2.5,
        period_sec: float = 4.19,  # ~1.5 rad/s: math.tau / 1.5 ≈ 4.1888s (~14.3 breaths/min)
    ):
        self.amplitude_px = max(1.0, min(5.0, float(amplitude_px)))
        self.period_sec = max(1.0, float(period_sec))
        self._start_time = time.monotonic()

    def update(self, current_time: Optional[float] = None) -> float:
        """Return the current vertical pixel offset in range [-amplitude_px, +amplitude_px]."""
        now = time.monotonic() if current_time is None else current_time
        elapsed = now - self._start_time
        return math.sin(elapsed * (math.tau / self.period_sec)) * self.amplitude_px

    def get_offset(self, anim_time: float) -> float:
        """Calculate breathing vertical offset directly from elapsed animation time."""
        return math.sin(anim_time * 1.5) * self.amplitude_px


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
        self.viseme_change_time = time.monotonic()
        self.current_amplitude = 0.0
        self.target_amplitude = 0.0

    def analyze_wav(self, wav_path: str, fps: int = 60) -> List[Dict[str, Any]]:
        """Convert a WAV file into a list of frame animation dicts containing:
        - 'amplitude': smoothed normalized RMS (0.0 to 1.0)
        - 'viseme': Preston-Blair viseme ('A' through 'H', 'X')
        - 'mouth_index': legacy 1, 2, 3 shape index
        - 'openness': continuous mouth aperture metric (0.0 to 1.0)
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

            # Temporal envelope smoothing: fast attack (~20ms) and smooth decay (~60ms)
            attack = 0.70
            decay = 0.30
            smoothed_rms = []
            env = 0.0
            for r in rms_list:
                if r > env:
                    env += attack * (r - env)
                else:
                    env += decay * (r - env)
                smoothed_rms.append(env)

            # Estimate visemes per frame
            raw_visemes = []
            norm_rms_list = []
            for i in range(num_frames):
                norm_rms = min(1.0, smoothed_rms[i] / (max_rms * 0.82)) if max_rms > 0 else 0.0
                norm_rms_list.append(norm_rms)
                frame_time_sec = i / float(fps)

                if rhubarb_cues:
                    v = self._get_viseme_from_cues(rhubarb_cues, frame_time_sec)
                else:
                    v = self._estimate_viseme(norm_rms, zcr_list[i])
                raw_visemes.append(v)

            # Coarticulation filter: smooth out isolated single-frame oscillations (flutters)
            coarticulated_visemes = list(raw_visemes)
            for i in range(1, num_frames - 1):
                prev_v = coarticulated_visemes[i - 1]
                next_v = raw_visemes[i + 1]
                cur_v = coarticulated_visemes[i]
                if prev_v == next_v and cur_v != prev_v and cur_v not in ("X", "A"):
                    coarticulated_visemes[i] = prev_v

            for i in range(num_frames):
                norm_rms = norm_rms_list[i]
                viseme = coarticulated_visemes[i]
                mouth_index = self.viseme_to_legacy_index(viseme)
                openness = self.viseme_to_openness(viseme, norm_rms)

                frames_data.append({
                    "amplitude": round(norm_rms, 3),
                    "viseme": viseme,
                    "mouth_index": mouth_index,
                    "openness": round(openness, 3),
                })

            return frames_data

        except Exception as e:
            print(f"[LipSync] Notice: Could not analyze WAV {wav_path} ({e}). Generating synthetic viseme stream.")
            return [
                {
                    "amplitude": round(0.3 * (1 + math.sin(i * 0.4)), 3),
                    "viseme": ("B" if (i // 4) % 2 == 0 else "C"),
                    "mouth_index": (2 if (i // 4) % 2 == 0 else 3),
                    "openness": round(0.4 * (1 + math.sin(i * 0.4)), 3),
                }
                for i in range(fps * 3)
            ]

    def viseme_to_openness(self, viseme: str, amplitude: float = 0.0) -> float:
        """Calculate continuous openness metric (0.0 to 1.0) combining viseme shape and acoustic amplitude."""
        base_openness = {
            "X": 0.0,
            "A": 0.05,
            "B": 0.25,
            "F": 0.35,
            "G": 0.35,
            "E": 0.50,
            "H": 0.55,
            "C": 0.70,
            "D": 0.95,
        }.get(viseme.upper(), 0.1)
        amp = max(0.0, min(1.0, float(amplitude)))
        return min(1.0, max(0.0, base_openness * (0.7 + 0.4 * amp)))

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

    def set_active_viseme(self, viseme: str, amplitude: Optional[float] = None) -> None:
        """Update active viseme and track transition time for smooth alpha cross-fading."""
        viseme = viseme.upper()
        if viseme != self.current_viseme:
            self.previous_viseme = self.current_viseme
            self.current_viseme = viseme
            self.viseme_change_time = time.monotonic()
        if amplitude is not None:
            self.target_amplitude = max(0.0, min(1.0, float(amplitude)))

    def get_crossfade_alpha(self) -> float:
        """Returns 0.0 to 1.0 progress of the transition between previous and current viseme."""
        if self.crossfade_duration <= 0:
            return 1.0
        elapsed = time.monotonic() - self.viseme_change_time
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


class TransitionSequencePlayer:
    """Manages high-performance playback of pre-decoded transition & animation frame sequences in Pygame.

    Designed for zero CPU video decoding overhead on Raspberry Pi 5.
    Features:
    - Smooth cadence pacing (native 24 fps) without frame dropping.
    - Viewport pre-scaling cache so smoothscale is NEVER called per-frame during render.
    - Multi-frame alpha cross-dissolve at both in-point and out-point for seamless visual handoffs.
    - Transition locking to prevent thrashing between states.
    - On-demand loading for idle animation frame directories.
    """

    def __init__(self, fps: float = 24.0, crossfade_frames: int = 6):
        self.fps = max(1.0, float(fps))
        self.crossfade_frames = max(0, int(crossfade_frames))
        self.active_sequence_id: Optional[str] = None
        self.frames: List[Any] = []
        self.is_playing: bool = False
        self.is_locked: bool = False
        self.current_frame_index: int = 0
        self.start_time: float = 0.0
        self.on_complete: Optional[Callable[[], None]] = None
        self.sequences: Dict[str, Any] = {}
        self.sequence_metadata: Dict[str, Dict[str, Any]] = {}
        # Viewport scaled cache: (sequence_id, width, height) -> List[pygame.Surface]
        self._scaled_cache: Dict[Tuple[str, int, int], List[Any]] = {}
        self.outgoing_surface: Optional[Any] = None
        self.incoming_surface: Optional[Any] = None

    def register_sequence(
        self,
        sequence_id: str,
        frames_or_dir: Any,
        label: str = "",
        fps: Optional[float] = None,
    ) -> None:
        """Register a pre-decoded sequence of frame surfaces or directory path."""
        self.sequences[sequence_id] = frames_or_dir
        self.sequence_metadata[sequence_id] = {
            "label": label or sequence_id.replace("_", " ").title(),
            "fps": fps or self.fps,
        }

    def load_from_directory(
        self,
        sequence_id: str,
        directory_path: str,
        fps: Optional[float] = None,
        label: str = "",
    ) -> int:
        """Eagerly pre-load frames from directory into pygame surfaces."""
        import pygame
        if not os.path.isdir(directory_path):
            return 0
        frame_files = [f for f in os.listdir(directory_path) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        frames = []
        for f in sorted(frame_files):
            try:
                surf = pygame.image.load(os.path.join(directory_path, f)).convert()
                frames.append(surf)
            except Exception as e:
                print(f"[TransitionSequencePlayer] Error loading frame {f}: {e}")
        if frames:
            self.register_sequence(sequence_id, frames, label=label, fps=fps)
            print(f"[TransitionSequencePlayer] Loaded '{sequence_id}' with {len(frames)} frames from {directory_path}")
        return len(frames)

    def has_sequence(self, sequence_id: str) -> bool:
        return sequence_id in self.sequences

    def play(
        self,
        sequence_id: str,
        on_complete: Optional[Callable[[], None]] = None,
        restart: bool = True,
        lock: bool = False,
        outgoing_surface: Optional[Any] = None,
        incoming_surface: Optional[Any] = None,
        crossfade_frames: int = 6,
    ) -> bool:
        """Begin playing a registered transition sequence."""
        if self.is_locked:
            return False

        seq = self.sequences.get(sequence_id)
        if not seq:
            return False

        # Load frames if registered as directory path
        if isinstance(seq, str) and os.path.isdir(seq):
            try:
                import pygame
                frame_files = [f for f in os.listdir(seq) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
                loaded = [pygame.image.load(os.path.join(seq, f)).convert() for f in sorted(frame_files)]
                if loaded:
                    self.sequences[sequence_id] = loaded
                    seq = loaded
                else:
                    return False
            except Exception as exc:
                print(f"[TransitionSequencePlayer] Error loading sequence '{sequence_id}': {exc}")
                return False

        if self.is_playing and self.active_sequence_id == sequence_id and not restart:
            return True

        self.active_sequence_id = sequence_id
        self.frames = seq
        self.is_playing = True
        self.is_locked = lock
        self.current_frame_index = 0
        now = time.monotonic()
        self.start_time = now
        self.on_complete = on_complete
        self.outgoing_surface = outgoing_surface
        self.incoming_surface = incoming_surface
        self.crossfade_frames = crossfade_frames
        return True

    def get_scaled_frames(self, target_size: Tuple[int, int]) -> List[Any]:
        """Retrieve or create viewport-scaled surfaces for active sequence."""
        if not self.active_sequence_id or not self.frames:
            return self.frames

        cache_key = (self.active_sequence_id, target_size[0], target_size[1])
        scaled = self._scaled_cache.get(cache_key)
        if scaled is None:
            import pygame
            if self.frames and hasattr(self.frames[0], "get_size") and self.frames[0].get_size() == target_size:
                scaled = self.frames
            else:
                scaled = []
                for f in self.frames:
                    if hasattr(f, "get_size"):
                        scaled.append(pygame.transform.smoothscale(f, target_size))
                    else:
                        scaled.append(f)
            self._scaled_cache[cache_key] = scaled
            if len(self._scaled_cache) > 4:
                oldest = next(iter(self._scaled_cache))
                del self._scaled_cache[oldest]
        return scaled

    def update(self, target_size: Optional[Tuple[int, int]] = None) -> Optional[Any]:
        """Call once per render tick. Returns the active frame surface or None."""
        if not self.is_playing or not self.frames:
            return None

        seq_fps = self.sequence_metadata.get(self.active_sequence_id, {}).get("fps", self.fps)
        elapsed = time.monotonic() - self.start_time
        target_frame = int(elapsed * seq_fps)

        if target_frame >= len(self.frames):
            active_list = self.get_scaled_frames(target_size) if target_size else self.frames
            final = active_list[-1]
            if self.incoming_surface is not None and self.crossfade_frames:
                import pygame
                final = self.incoming_surface
                if target_size and hasattr(final, "get_size") and final.get_size() != target_size:
                    final = pygame.transform.smoothscale(final, target_size)
            self.is_playing = False
            self.is_locked = False
            self.current_frame_index = len(self.frames) - 1
            cb = self.on_complete
            self.on_complete = None
            if cb:
                try:
                    cb()
                except Exception as exc:
                    print(f"[TransitionSequencePlayer] Error in on_complete: {exc}")
            return final

        self.current_frame_index = target_frame
        active_list = self.get_scaled_frames(target_size) if target_size else self.frames
        current_surf = active_list[self.current_frame_index]

        # Apply smooth alpha crossfade at in-point and out-point if surfaces provided
        if self.crossfade_frames > 0 and len(self.frames) > self.crossfade_frames * 2:
            import pygame
            # In-point crossfade: blend outgoing_surface -> transition sequence
            if self.current_frame_index < self.crossfade_frames and self.outgoing_surface is not None:
                alpha = self.current_frame_index / float(self.crossfade_frames)
                try:
                    out_scaled = self.outgoing_surface
                    if target_size and hasattr(out_scaled, "get_size") and out_scaled.get_size() != target_size:
                        out_scaled = pygame.transform.smoothscale(out_scaled, target_size)
                    blended = out_scaled.copy()
                    top = current_surf.copy()
                    top.set_alpha(int(alpha * 255))
                    blended.blit(top, (0, 0))
                    return blended
                except Exception:
                    pass

            # Out-point crossfade: blend transition sequence -> incoming_surface
            remaining = len(self.frames) - 1 - self.current_frame_index
            if remaining < self.crossfade_frames and self.incoming_surface is not None:
                alpha = remaining / float(self.crossfade_frames)
                try:
                    in_scaled = self.incoming_surface
                    if target_size and hasattr(in_scaled, "get_size") and in_scaled.get_size() != target_size:
                        in_scaled = pygame.transform.smoothscale(in_scaled, target_size)
                    blended = in_scaled.copy()
                    top = current_surf.copy()
                    top.set_alpha(int(alpha * 255))
                    blended.blit(top, (0, 0))
                    return blended
                except Exception:
                    pass

        return current_surf

    def get_current_frame(self) -> Optional[Any]:
        if self.frames and 0 <= self.current_frame_index < len(self.frames):
            return self.frames[self.current_frame_index]
        return None

    def get_native_size(self):
        frame = self.get_current_frame()
        return frame.get_size() if hasattr(frame, "get_size") else None

    def unlock(self):
        """Explicit debug override; normal play requests cannot bypass a lock."""
        self.is_locked = False

    def stop(self) -> None:
        self.is_playing = False
        self.is_locked = False
        self.on_complete = None

    def get_progress(self) -> float:
        if not self.frames or not self.is_playing:
            return 1.0 if not self.is_playing else 0.0
        return min(1.0, max(0.0, self.current_frame_index / max(1, len(self.frames) - 1)))


class IdleActivityController:
    """Manages Wilhelm's autonomous daily activities and periodic gestures when idle."""

    def __init__(
        self,
        default_activity: str = "reading",
        action_interval_min: float = 25.0,
        action_interval_max: float = 50.0,
    ):
        self.current_activity = default_activity
        self.action_interval_min = action_interval_min
        self.action_interval_max = action_interval_max
        self._last_action_time = time.monotonic()
        self._next_action_time = self._last_action_time + random.uniform(
            self.action_interval_min, self.action_interval_max
        )
        self.pending_idle_action: Optional[str] = None
        self.activities: Dict[str, Dict[str, Any]] = {
            "reading": {
                "base_sprite": "wilhelm_reading",
                "periodic_actions": ["page_flip"],
            },
            "tinkering": {
                "base_sprite": "wilhelm_tinker",
                "periodic_actions": ["tinker_box_study"],
            },
        }

    def register_activity(self, name: str, base_sprite: str, periodic_actions: List[str]) -> None:
        self.activities[name] = {
            "base_sprite": base_sprite,
            "periodic_actions": periodic_actions,
        }

    def update(self) -> Optional[str]:
        now = time.monotonic()
        if now >= self._next_action_time:
            self._last_action_time = now
            self._next_action_time = now + random.uniform(
                self.action_interval_min, self.action_interval_max
            )
            act_info = self.activities.get(self.current_activity)
            if act_info and act_info.get("periodic_actions"):
                action = random.choice(act_info["periodic_actions"])
                self.pending_idle_action = action
                return action
        return None

    def set_activity(self, activity_name: str) -> None:
        if activity_name in self.activities:
            self.current_activity = activity_name
            self._last_action_time = time.monotonic()
            self._next_action_time = self._last_action_time + random.uniform(
                self.action_interval_min, self.action_interval_max
            )


class DeskFaceRig:
    """Dynamic facial articulation rig for Wilhelm's desk view in Scene Director mode.

    Articulates:
    - Preston-Blair or amplitude-driven mouth visemes during speech.
    - Biological eyelid blinks with natural easing (180ms ease-in/out every 2.5-5.5s).
    - Visitor gaze tracking & micro-saccades (1-2px ocular tremor).
    - Subtle chest breathing drift (2-3px sinusoidal vertical offset).
    """

    def __init__(
        self,
        face_rel_x: float = 0.5756,
        face_rel_y: float = 0.3333,
        reference_canvas_size: Tuple[int, int] = (1280, 720),
    ):
        self.face_rel_x = float(face_rel_x)
        self.face_rel_y = float(face_rel_y)
        self.reference_canvas_size = reference_canvas_size

        # Continuous mouth interpolation and amplitude state across frames
        self._mouth_initialized = False
        self._last_mouth_time = time.monotonic()
        self.cur_w = 30.0
        self.cur_h = 3.5
        self.cur_offset_y = 0.0
        self.cur_teeth_w = 0.0
        self.cur_teeth_h = 0.0
        self.cur_teeth_y = 0.0
        self.cur_tongue_w = 0.0
        self.cur_tongue_h = 0.0
        self.cur_tongue_y = 0.0
        self.cur_cav_r = 90.0
        self.cur_cav_g = 35.0
        self.cur_cav_b = 30.0
        self.cur_amplitude = 0.0

    def _reset_mouth_state(self) -> None:
        """Reset mouth interpolation back to resting shape."""
        self._mouth_initialized = False
        self.cur_w = 30.0
        self.cur_h = 3.5
        self.cur_offset_y = 0.0
        self.cur_teeth_w = 0.0
        self.cur_teeth_h = 0.0
        self.cur_teeth_y = 0.0
        self.cur_tongue_w = 0.0
        self.cur_tongue_h = 0.0
        self.cur_tongue_y = 0.0
        self.cur_cav_r = 90.0
        self.cur_cav_g = 35.0
        self.cur_cav_b = 30.0
        self.cur_amplitude = 0.0

    def get_face_geometry(
        self,
        target_size: Tuple[int, int],
        dest: Tuple[int, int],
        head_yaw_x: float = 0.0,
        head_pitch_y: float = 0.0,
        breath_offset: float = 0.0,
    ) -> Dict[str, Any]:
        """Compute pixel positions and dimensions for face, eyes, and mouth."""
        ref_w, ref_h = self.reference_canvas_size
        scale_x = target_size[0] / float(ref_w)
        scale_y = target_size[1] / float(ref_h)
        face_scale = min(scale_x, scale_y)

        face_cx = dest[0] + int(target_size[0] * self.face_rel_x) + int(head_yaw_x * scale_x)
        face_cy = dest[1] + int(target_size[1] * self.face_rel_y) + int((breath_offset + head_pitch_y) * scale_y)

        # Eye locations relative to face center
        left_eye_cx = face_cx - int(20 * scale_x)
        left_eye_cy = face_cy - int(14 * scale_y)
        right_eye_cx = face_cx + int(26 * scale_x)
        right_eye_cy = face_cy - int(14 * scale_y)

        eye_w = max(6, int(18 * scale_x))
        eye_h = max(4, int(11 * scale_y))
        iris_r = max(2, int(4.5 * face_scale))
        pupil_r = max(1, int(2.5 * face_scale))

        # Mouth location relative to face center
        mouth_cx = face_cx + int(2 * scale_x)
        mouth_cy = face_cy + int(32 * scale_y)

        return {
            "face_center": (face_cx, face_cy),
            "face_scale": face_scale,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "left_eye": (left_eye_cx, left_eye_cy),
            "right_eye": (right_eye_cx, right_eye_cy),
            "eye_size": (eye_w, eye_h),
            "iris_radius": iris_r,
            "pupil_radius": pupil_r,
            "mouth_center": (mouth_cx, mouth_cy),
        }

    def render_eyes(
        self,
        surface: Any,
        geometry: Dict[str, Any],
        blink_stage: str,
        closure_progress: float,
        pupil_x: float,
        pupil_y: float,
        sprites: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Render biological eased blinks, irises, pupils, and micro-saccades onto the surface."""
        import pygame

        face_scale = geometry["face_scale"]
        scale_x = geometry["scale_x"]
        scale_y = geometry["scale_y"]
        eye_w, eye_h = geometry["eye_size"]
        iris_r = geometry["iris_radius"]
        pupil_r = geometry["pupil_radius"]

        # Pupil offset clamped within eye boundaries
        max_px = max(1, int(4 * scale_x))
        max_py = max(1, int(2.5 * scale_y))
        px = max(-max_px, min(max_px, int(pupil_x * scale_x)))
        py = max(-max_py, min(max_py, int(pupil_y * scale_y)))

        for eye_cx, eye_cy in (geometry["left_eye"], geometry["right_eye"]):
            if blink_stage == "closed":
                # Eased fully closed eyelid skin fill
                lid_rect = pygame.Rect(eye_cx - eye_w // 2, eye_cy - eye_h // 2, eye_w, eye_h)
                pygame.draw.ellipse(surface, (215, 175, 145), lid_rect)
                # Crease and closed lash line
                arc_rect = pygame.Rect(eye_cx - eye_w // 2, eye_cy - eye_h // 4, eye_w, max(2, eye_h // 2 + 2))
                pygame.draw.arc(surface, (55, 38, 25), arc_rect, 3.14, 6.28, max(1, int(2 * face_scale)))
            else:
                # White Sclera
                sclera_rect = pygame.Rect(eye_cx - eye_w // 2, eye_cy - eye_h // 2, eye_w, eye_h)
                pygame.draw.ellipse(surface, (242, 240, 235), sclera_rect)

                # Blue-Grey Iris
                pygame.draw.circle(surface, (70, 110, 160), (eye_cx + px, eye_cy + py), iris_r)
                # Charcoal Pupil
                pygame.draw.circle(surface, (15, 20, 30), (eye_cx + px, eye_cy + py), pupil_r)
                # Specular Catchlight
                catch_r = max(1, int(1.0 * face_scale))
                pygame.draw.circle(surface, (255, 255, 255), (eye_cx + px - 1, eye_cy + py - 1), catch_r)
                # Upper lash / eyelid fold contour
                pygame.draw.arc(surface, (70, 50, 35), sclera_rect, 0.0, 3.14, max(1, int(1.5 * face_scale)))

                # Eased Half-Closed Eyelid Overlay
                if blink_stage == "half":
                    drop_h = max(2, int(eye_h * max(0.2, min(0.9, closure_progress))))
                    lid_rect = pygame.Rect(eye_cx - eye_w // 2, eye_cy - eye_h // 2, eye_w, drop_h)
                    pygame.draw.rect(surface, (215, 175, 145), lid_rect)
                    crease_rect = pygame.Rect(eye_cx - eye_w // 2, eye_cy - eye_h // 2 + drop_h - 2, eye_w, max(2, int(4 * face_scale)))
                    pygame.draw.arc(surface, (75, 45, 30), crease_rect, 3.14, 6.28, max(1, int(2 * face_scale)))

    def render_mouth(
        self,
        surface: Any,
        geometry: Dict[str, Any],
        viseme: str,
        mouth_index: int,
        is_speaking: bool = True,
        crossfade_alpha: float = 1.0,
        sprites: Optional[Dict[str, Any]] = None,
        amplitude: Optional[float] = None,
        **kwargs,
    ) -> None:
        """Render Preston-Blair viseme lip-sync with smooth continuous interpolation and amplitude modulation."""
        import pygame

        v = str(viseme).strip().upper()
        if v not in VISEME_NAMES:
            v = "X"

        if not is_speaking and v in ("X", "A"):
            self._reset_mouth_state()
            return  # Retain natural resting mouth of the held video frame

        mouth_cx, mouth_cy = geometry["mouth_center"]
        scale_x = geometry["scale_x"]
        scale_y = geometry["scale_y"]
        face_scale = geometry["face_scale"]

        # Check for authored cropped transparent mouth sprite
        if sprites:
            sprite = sprites.get(f"viseme_{v}") or sprites.get(f"mouth_{mouth_index}")
            if sprite is not None:
                max_overlay_w = int(geometry["scale_x"] * self.reference_canvas_size[0] * 0.4)
                if (sprite.get_flags() & pygame.SRCALPHA) and sprite.get_width() < max_overlay_w:
                    scaled_w = max(4, int(sprite.get_width() * face_scale))
                    scaled_h = max(4, int(sprite.get_height() * face_scale))
                    scaled_sprite = pygame.transform.smoothscale(sprite, (scaled_w, scaled_h))
                    surface.blit(scaled_sprite, (mouth_cx - scaled_w // 2, mouth_cy - scaled_h // 2))
                    return

        # Target mouth parameters for Preston-Blair visemes:
        # (width, height, offset_y, teeth_w, teeth_h, teeth_y, tongue_w, tongue_h, tongue_y, cavity_rgb)
        specs: Dict[str, Tuple[float, float, float, float, float, float, float, float, float, Tuple[int, int, int]]] = {
            "A": (30.0, 3.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (90, 35, 30)),
            "X": (30.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, (90, 35, 30)),
            "B": (28.0, 8.0, -2.0, 18.0, 3.0, -2.0, 0.0, 0.0, 0.0, (65, 18, 18)),
            "C": (34.0, 13.0, -4.0, 20.0, 4.0, -4.0, 14.0, 6.0, 3.0, (60, 15, 15)),
            "D": (38.0, 18.0, -6.0, 24.0, 5.0, -6.0, 18.0, 7.0, 4.0, (45, 10, 10)),
            "E": (22.0, 13.0, -5.0, 12.0, 3.0, -5.0, 0.0, 0.0, 0.0, (50, 12, 12)),
            "F": (14.0, 14.0, 2.0, 6.0, 6.0, 1.0, 0.0, 0.0, 0.0, (55, 14, 14)),
            "G": (26.0, 8.0, -2.0, 18.0, 4.0, -2.0, 0.0, 0.0, 0.0, (70, 20, 20)),
            "H": (30.0, 13.0, -4.0, 18.0, 3.0, -4.0, 12.0, 6.0, -1.0, (55, 15, 15)),
        }

        spec = specs.get(v, specs["X"])
        target_w, target_h, target_offset_y, target_teeth_w, target_teeth_h, target_teeth_y, target_tongue_w, target_tongue_h, target_tongue_y, target_cavity = spec

        # Fallback adjustment from legacy mouth_index if viseme was X or A during speech
        if v in ("X", "A") and mouth_index == 2:
            spec_b = specs["B"]
            target_w, target_h, target_offset_y = spec_b[0], spec_b[1], spec_b[2]
            target_teeth_w, target_teeth_h, target_teeth_y = spec_b[3], spec_b[4], spec_b[5]
            target_cavity = spec_b[9]
        elif v in ("X", "A") and mouth_index == 3:
            spec_d = specs["D"]
            target_w, target_h, target_offset_y = spec_d[0], spec_d[1], spec_d[2]
            target_teeth_w, target_teeth_h, target_teeth_y = spec_d[3], spec_d[4], spec_d[5]
            target_tongue_w, target_tongue_h, target_tongue_y = spec_d[6], spec_d[7], spec_d[8]
            target_cavity = spec_d[9]

        # Dynamic amplitude modulation: scale mouth opening with acoustic energy
        if amplitude is not None:
            eff_amp = max(0.0, min(1.0, float(amplitude)))
        else:
            eff_amp = 0.85 if mouth_index == 3 else (0.45 if mouth_index == 2 else 0.15)

        # Subtle expansion on higher acoustic energy (0.75x to 1.25x)
        amp_scale = 0.75 + 0.50 * eff_amp
        target_h *= amp_scale
        target_w *= (0.90 + 0.20 * eff_amp)
        if target_teeth_w > 0:
            target_teeth_w *= (0.90 + 0.20 * eff_amp)
        if target_tongue_w > 0:
            target_tongue_w *= (0.90 + 0.20 * eff_amp)

        now = time.monotonic()
        delta = min(0.05, max(0.0, now - self._last_mouth_time))
        self._last_mouth_time = now

        if not self._mouth_initialized:
            self._mouth_initialized = True
            self.cur_w = target_w
            self.cur_h = target_h
            self.cur_offset_y = target_offset_y
            self.cur_teeth_w = target_teeth_w
            self.cur_teeth_h = target_teeth_h
            self.cur_teeth_y = target_teeth_y
            self.cur_tongue_w = target_tongue_w
            self.cur_tongue_h = target_tongue_h
            self.cur_tongue_y = target_tongue_y
            self.cur_cav_r = float(target_cavity[0])
            self.cur_cav_g = float(target_cavity[1])
            self.cur_cav_b = float(target_cavity[2])
        else:
            # Smooth exponential interpolation between successive frames (~40ms time constant)
            blend_rate = 24.0
            lerp = 1.0 - math.exp(-blend_rate * delta) if delta > 0 else 1.0
            self.cur_w += (target_w - self.cur_w) * lerp
            self.cur_h += (target_h - self.cur_h) * lerp
            self.cur_offset_y += (target_offset_y - self.cur_offset_y) * lerp
            self.cur_teeth_w += (target_teeth_w - self.cur_teeth_w) * lerp
            self.cur_teeth_h += (target_teeth_h - self.cur_teeth_h) * lerp
            self.cur_teeth_y += (target_teeth_y - self.cur_teeth_y) * lerp
            self.cur_tongue_w += (target_tongue_w - self.cur_tongue_w) * lerp
            self.cur_tongue_h += (target_tongue_h - self.cur_tongue_h) * lerp
            self.cur_tongue_y += (target_tongue_y - self.cur_tongue_y) * lerp
            self.cur_cav_r += (float(target_cavity[0]) - self.cur_cav_r) * lerp
            self.cur_cav_g += (float(target_cavity[1]) - self.cur_cav_g) * lerp
            self.cur_cav_b += (float(target_cavity[2]) - self.cur_cav_b) * lerp

        mw = max(4, int(self.cur_w * scale_x))
        mh = max(2, int(self.cur_h * scale_y))
        my_off = int(self.cur_offset_y * scale_y)
        cav_color = (
            max(0, min(255, int(self.cur_cav_r))),
            max(0, min(255, int(self.cur_cav_g))),
            max(0, min(255, int(self.cur_cav_b))),
        )

        if v in ("A", "X") and self.cur_h <= 4.5 and mouth_index == 1:
            # Closed mouth resting line
            pygame.draw.ellipse(surface, (90, 35, 30), (mouth_cx - mw // 2, mouth_cy + my_off, mw, mh))
        else:
            # Oral cavity
            cavity_rect = pygame.Rect(mouth_cx - mw // 2, mouth_cy + my_off, mw, mh)
            pygame.draw.ellipse(surface, cav_color, cavity_rect)

            # Upper teeth
            if self.cur_teeth_w > 2.0 and self.cur_teeth_h > 1.0:
                tw = max(2, int(self.cur_teeth_w * scale_x))
                th = max(1, int(self.cur_teeth_h * scale_y))
                ty_off = int(self.cur_teeth_y * scale_y)
                teeth_rect = pygame.Rect(mouth_cx - tw // 2, mouth_cy + ty_off, tw, th)
                pygame.draw.rect(surface, (245, 245, 245), teeth_rect)

            # Tongue
            if self.cur_tongue_w > 2.0 and self.cur_tongue_h > 1.0:
                tgw = max(2, int(self.cur_tongue_w * scale_x))
                tgh = max(1, int(self.cur_tongue_h * scale_y))
                tgy_off = int(self.cur_tongue_y * scale_y)
                tongue_rect = pygame.Rect(mouth_cx - tgw // 2, mouth_cy + tgy_off, tgw, tgh)
                pygame.draw.ellipse(surface, (180, 60, 70), tongue_rect)

    def render(
        self,
        surface: Any,
        target_size: Tuple[int, int],
        dest: Tuple[int, int],
        blink_stage: str,
        closure_progress: float,
        viseme: str,
        mouth_index: int,
        pupil_x: float,
        pupil_y: float,
        is_speaking: bool = True,
        breath_offset: float = 0.0,
        head_yaw_x: float = 0.0,
        head_pitch_y: float = 0.0,
        sprites: Optional[Dict[str, Any]] = None,
        amplitude: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Articulate full face: biological blinks, pupil gaze/saccades, and lipsync mouth."""
        geometry = self.get_face_geometry(
            target_size=target_size,
            dest=dest,
            head_yaw_x=head_yaw_x,
            head_pitch_y=head_pitch_y,
            breath_offset=breath_offset,
        )
        self.render_eyes(
            surface=surface,
            geometry=geometry,
            blink_stage=blink_stage,
            closure_progress=closure_progress,
            pupil_x=pupil_x,
            pupil_y=pupil_y,
            sprites=sprites,
        )
        self.render_mouth(
            surface=surface,
            geometry=geometry,
            viseme=viseme,
            mouth_index=mouth_index,
            is_speaking=is_speaking,
            sprites=sprites,
            amplitude=amplitude,
            **kwargs,
        )
        return geometry
