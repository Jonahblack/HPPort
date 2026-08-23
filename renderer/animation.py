"""Animation helpers: Lip-sync RMS waveform analyzer and natural blink timer."""

import random
import time
import wave
import numpy as np
from typing import List, Tuple, Dict, Any


class LipSyncEngine:
    """Computes RMS amplitude slices from WAV audio for real-time mouth sprite flapping."""

    def __init__(self, threshold_mouth_2: float = 0.15, threshold_mouth_3: float = 0.45):
        self.threshold_mouth_2 = threshold_mouth_2
        self.threshold_mouth_3 = threshold_mouth_3

    def analyze_wav(self, wav_path: str, fps: int = 60) -> List[float]:
        """Convert a WAV file into normalized RMS amplitude per video frame (~16-33ms)."""
        try:
            with wave.open(wav_path, "rb") as wf:
                channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                raw_bytes = wf.readframes(nframes)

            # Convert to numpy array
            if sampwidth == 2:
                samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
            else:
                samples = np.frombuffer(raw_bytes, dtype=np.int8).astype(np.float32)

            if channels > 1:
                samples = samples[::channels]

            # Samples per frame slice
            samples_per_frame = max(1, int(framerate / fps))
            num_frames = int(np.ceil(len(samples) / samples_per_frame))

            amplitudes = []
            max_rms = 1.0

            for i in range(num_frames):
                start = i * samples_per_frame
                end = min(len(samples), start + samples_per_frame)
                chunk = samples[start:end]
                if len(chunk) > 0:
                    rms = np.sqrt(np.mean(chunk**2))
                    amplitudes.append(rms)
                    if rms > max_rms:
                        max_rms = rms
                else:
                    amplitudes.append(0.0)

            # Normalize to 0.0 - 1.0 range
            if max_rms > 0:
                normalized = [min(1.0, a / (max_rms * 0.85)) for a in amplitudes]
            else:
                normalized = [0.0] * len(amplitudes)

            return normalized

        except Exception as e:
            print(f"[LipSync] Warning: Could not analyze WAV {wav_path} ({e}). Using simulated flapping.")
            return [0.3 * (1 + np.sin(i * 0.4)) for i in range(fps * 3)]

    def get_mouth_shape_index(self, amplitude: float) -> int:
        """Return mouth sprite index (1 = closed, 2 = partial, 3 = wide)."""
        if amplitude >= self.threshold_mouth_3:
            return 3
        elif amplitude >= self.threshold_mouth_2:
            return 2
        return 1


class BlinkController:
    """Randomized natural eye-blink timer."""

    def __init__(self, min_interval_sec: float = 2.0, max_interval_sec: float = 5.0, blink_duration_ms: int = 150):
        self.min_interval = min_interval_sec
        self.max_interval = max_interval_sec
        self.blink_duration_sec = blink_duration_ms / 1000.0

        self.next_blink_time = time.time() + random.uniform(self.min_interval, self.max_interval)
        self.is_blinking = False
        self.blink_end_time = 0.0

    def update(self) -> bool:
        """Call each frame. Returns True if eyes should be closed."""
        now = time.time()

        if not self.is_blinking:
            if now >= self.next_blink_time:
                self.is_blinking = True
                self.blink_end_time = now + self.blink_duration_sec
        else:
            if now >= self.blink_end_time:
                self.is_blinking = False
                self.next_blink_time = now + random.uniform(self.min_interval, self.max_interval)

        return self.is_blinking
