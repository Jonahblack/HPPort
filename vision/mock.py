import math
import time
from typing import Dict, Any, Optional, Tuple
from vision.base import BaseVisionDetector

class MockVision(BaseVisionDetector):
    """Simulated person detector controlled via spacebar, API triggers, or timer."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._running = False
        self._detected = False
        self._confidence = 0.0
        self._trigger_until = 0.0
        self.cam_width = 320
        self.cam_height = 240
        self._start_time = time.monotonic()
        self._preview_key = None
        self._preview_surface = None

    def start(self) -> None:
        self._running = True
        print("[Vision] MockVision sensor active (Press SPACE to trigger presence).")

    def stop(self) -> None:
        self._running = False

    def is_person_detected(self) -> bool:
        if not self._running:
            return False
        if time.monotonic() < self._trigger_until:
            return True
        return self._detected

    def get_confidence(self) -> float:
        if self.is_person_detected():
            return max(0.75, self._confidence or 0.90)
        return 0.0

    def trigger(self, duration_seconds: float = 4.0) -> None:
        """Trigger a simulated person arrival event."""
        self._trigger_until = time.monotonic() + duration_seconds
        self._confidence = 0.94
        print(f"[Vision] Simulated person arrival triggered for {duration_seconds}s!")

    def set_detected(self, detected: bool, confidence: float = 0.88) -> None:
        self._detected = detected
        self._confidence = confidence if detected else 0.0

    def get_latest_frame(self, target_size: Optional[Tuple[int, int]] = None) -> Optional[Any]:
        """Generate animated synthetic radar surface for Pygame preview."""
        elapsed = time.monotonic() - self._start_time
        is_present = self.is_person_detected()
        key = (int(elapsed * 15), target_size, is_present)
        if key == self._preview_key:
            return self._preview_surface
        try:
            import pygame  # type: ignore
            w, h = target_size or (self.cam_width, self.cam_height)
            surface = pygame.Surface((w, h))
            surface.fill((14, 22, 28))
            spacing = max(10, w // 10)
            for x in range(0, w, spacing):
                pygame.draw.line(surface, (30, 48, 62), (x, 0), (x, h))
            for y in range(0, h, spacing):
                pygame.draw.line(surface, (30, 48, 62), (0, y), (w, y))
            if is_present:
                px = w // 2 + int(math.sin(elapsed * 1.5) * w / 4)
                py = h // 2
                radius = max(4, w // 10)
                pygame.draw.circle(surface, (52, 211, 153), (px, py), radius)
                rect = pygame.Rect(px - radius, py - radius, radius * 2, radius * 2)
                pygame.draw.rect(surface, (52, 211, 153), rect, width=2)
            scan_y = int(elapsed * 90) % h
            pygame.draw.line(surface, (56, 189, 248), (0, scan_y), (w, scan_y), 2)
            self._preview_key = key
            self._preview_surface = surface
            return surface
        except Exception:
            return None

    def get_status_info(self) -> Dict[str, Any]:
        return {
            "driver": "mock_vision",
            "active": self._running,
            "fps": 30.0,
            "detected": self.is_person_detected(),
            "confidence": round(self.get_confidence(), 2),
        }

    def get_visitor_gaze(self) -> Tuple[float, float, float]:
        if not self.is_person_detected():
            return (0.0, 0.0, 1.0)
        elapsed = time.monotonic() - self._start_time
        norm_x = math.sin(elapsed * 1.5)
        norm_y = 0.15 * math.cos(elapsed * 0.9)
        distance = 1.0 + 0.2 * math.sin(elapsed * 0.6)
        return (norm_x, norm_y, distance)
