"""
2D Layered Animation Controller for the Talking Portrait.
Handles natural eye blinking timing and audio-amplitude-synchronized mouth frames.
"""

from enum import Enum, auto
import logging
import random
import time
from typing import Optional

logger = logging.getLogger(__name__)


class MouthFrame(Enum):
    CLOSED = 1  # mouth_1.png (silence / very quiet)
    PARTIAL = 2  # mouth_2.png (medium amplitude)
    OPEN = 3  # mouth_3.png (high amplitude)


class AnimationController:
    """Calculates blink state and mouth frame based on time and audio amplitude."""

    def __init__(
        self,
        blink_min_seconds: float = 2.0,
        blink_max_seconds: float = 5.0,
        blink_duration_seconds: float = 0.15,
        threshold_mouth_2: float = 0.15,
        threshold_mouth_3: float = 0.45,
    ):
        self.blink_min_seconds = blink_min_seconds
        self.blink_max_seconds = blink_max_seconds
        self.blink_duration_seconds = blink_duration_seconds
        self.threshold_mouth_2 = threshold_mouth_2
        self.threshold_mouth_3 = threshold_mouth_3

        self.last_blink_time: float = time.time()
        self.next_blink_interval: float = self._get_random_blink_interval()
        self.is_blinking: bool = False
        self.current_amplitude: float = 0.0
        self.current_mouth_frame: MouthFrame = MouthFrame.CLOSED

    def _get_random_blink_interval(self) -> float:
        return random.uniform(self.blink_min_seconds, self.blink_max_seconds)

    def set_audio_amplitude(self, amplitude: float) -> None:
        """Update current audio amplitude (0.0 to 1.0) for mouth mapping."""
        self.current_amplitude = max(0.0, min(1.0, amplitude))
        if self.current_amplitude < self.threshold_mouth_2:
            self.current_mouth_frame = MouthFrame.CLOSED
        elif self.current_amplitude < self.threshold_mouth_3:
            self.current_mouth_frame = MouthFrame.PARTIAL
        else:
            self.current_mouth_frame = MouthFrame.OPEN

    def update(self) -> None:
        """Update blink timing."""
        now = time.time()
        elapsed_since_blink = now - self.last_blink_time

        if not self.is_blinking:
            if elapsed_since_blink >= self.next_blink_interval:
                self.is_blinking = True
                self.last_blink_time = now
        else:
            if now - self.last_blink_time >= self.blink_duration_seconds:
                self.is_blinking = False
                self.last_blink_time = now
                self.next_blink_interval = self._get_random_blink_interval()

    @property
    def eyes_closed(self) -> bool:
        return self.is_blinking

    @property
    def mouth_frame(self) -> MouthFrame:
        return self.current_mouth_frame
