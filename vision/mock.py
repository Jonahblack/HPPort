"""Mock vision driver for desktop development and manual testing."""

import time
from typing import Optional, Dict, Any
from vision.base import BaseVisionDetector


class MockVision(BaseVisionDetector):
    """Mock vision detector triggered by keyboard spacebar or simulated timed events."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._running = False
        self._detected = False
        self._confidence = 0.0
        self._last_trigger_time = 0.0

    def start(self) -> None:
        self._running = True
        print("[Vision] MockVision initialized. Press SPACE in Pygame window to trigger wake.")

    def stop(self) -> None:
        self._running = False

    def trigger(self, duration_seconds: float = 3.0) -> None:
        """Manually trigger detection for a specified duration."""
        self._detected = True
        self._confidence = 0.92
        self._last_trigger_time = time.time() + duration_seconds
        print(f"[Vision] Mock detection TRIGGERED (confidence: {self._confidence:.2f})")

    def is_person_detected(self) -> bool:
        if not self._running:
            return False

        if self._detected:
            if time.time() > self._last_trigger_time:
                self._detected = False
                self._confidence = 0.0
            return self._detected

        return False

    def get_confidence(self) -> float:
        return self._confidence if self.is_person_detected() else 0.0
