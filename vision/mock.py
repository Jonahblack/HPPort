"""
Mock Vision Detector for desktop development and automated testing.
Allows simulating visitor arrival via spacebar, API, or automated test hooks.
"""

import logging
import threading
import time
from typing import Callable, Optional

from .base import BaseVisionDetector, DetectionFrame

logger = logging.getLogger(__name__)


class MockVision(BaseVisionDetector):
    """Vision detector mock for rapid desktop testing without camera/Hailo hardware."""

    def __init__(self, poll_interval_seconds: float = 0.1):
        self.poll_interval_seconds = poll_interval_seconds
        self._is_running = False
        self._callback: Optional[Callable[[DetectionFrame], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._simulate_person = False
        self._last_detection = DetectionFrame(person_detected=False, timestamp=time.time())

    def is_running(self) -> bool:
        return self._is_running

    def get_last_detection(self) -> DetectionFrame:
        return self._last_detection

    def start(self, callback: Callable[[DetectionFrame], None]) -> None:
        if self._is_running:
            return

        self._callback = callback
        self._is_running = True
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("MockVision detector running. Use trigger_visitor() or Space key to simulate visitor arrival.")

    def stop(self) -> None:
        self._is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def trigger_visitor(self, confidence: float = 0.95, duration_frames: int = 5) -> None:
        """Simulate a person approaching and standing in front of the portrait."""
        logger.info("MockVision: Triggering simulated visitor arrival (confidence: %.2f)", confidence)
        self._simulate_person = True

        def _reset():
            time.sleep(duration_frames * self.poll_interval_seconds)
            self._simulate_person = False

        threading.Thread(target=_reset, daemon=True).start()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            frame = DetectionFrame(
                person_detected=self._simulate_person,
                confidence=0.92 if self._simulate_person else 0.0,
                bounding_box=(0.25, 0.2, 0.5, 0.6) if self._simulate_person else None,
                timestamp=time.time(),
            )
            self._last_detection = frame

            if self._callback:
                self._callback(frame)

            time.sleep(self.poll_interval_seconds)
