"""
Mock TTS engine for desktop development and automated testing.
Produces simulated audio playback durations and dynamic RMS amplitude envelopes.
"""

import logging
import math
import threading
import time
from typing import Callable, List, Optional

from .base import BaseTTS, TTSAudioResult, TTSMetrics

logger = logging.getLogger(__name__)


class MockTTS(BaseTTS):
    """Mock TTS simulator generating rhythmic amplitude curves for mouth synchronization."""

    def __init__(self, words_per_minute: int = 150):
        self.words_per_minute = words_per_minute
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def synthesize(self, text: str, output_path: Optional[str] = None) -> TTSAudioResult:
        start_time = time.time()
        words = text.strip().split()
        num_words = max(1, len(words))
        audio_dur = (num_words / self.words_per_minute) * 60.0

        # Generate realistic undulating speech amplitudes (0.0 to 1.0)
        num_frames = int(audio_dur * 30)
        amplitudes: List[float] = []
        for i in range(num_frames):
            # Syllable modulation + random jitter
            t = i * 0.033
            amp = (math.sin(t * 14.0) * 0.45 + 0.45) * (0.8 + 0.2 * math.sin(t * 3.0))
            if (i % 25) in (0, 1, 2):  # brief inter-word pause
                amp *= 0.1
            amplitudes.append(round(min(1.0, max(0.0, amp)), 3))

        gen_time = 0.05
        metrics = TTSMetrics(
            generation_time_seconds=gen_time,
            time_to_first_audio_seconds=0.02,
            audio_duration_seconds=audio_dur,
        )

        return TTSAudioResult(
            audio_path=output_path,
            raw_pcm=b"",
            sample_rate=22050,
            amplitudes=amplitudes,
            metrics=metrics,
        )

    def play_audio(
        self,
        audio_result: TTSAudioResult,
        amplitude_callback: Optional[Callable[[float], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        self.stop_playback()
        self._stop_event.clear()

        def _worker():
            amps = audio_result.amplitudes or [0.0]
            step_time = 0.033

            for amp in amps:
                if self._stop_event.is_set():
                    break
                if amplitude_callback:
                    amplitude_callback(amp)
                time.sleep(step_time)

            if amplitude_callback:
                amplitude_callback(0.0)

            if not self._stop_event.is_set() and on_finished:
                on_finished()

        self._playback_thread = threading.Thread(target=_worker, daemon=True)
        self._playback_thread.start()

    def stop_playback(self) -> None:
        self._stop_event.set()
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.5)
