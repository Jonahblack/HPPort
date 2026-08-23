"""Mock vision detector for desktop development and automated testing."""

import time
import numpy as np
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
        self.sim_tick = 0

    def start(self) -> None:
        self._running = True
        print("[Vision] MockVision sensor active (Press SPACE to trigger presence).")

    def stop(self) -> None:
        self._running = False

    def is_person_detected(self) -> bool:
        if not self._running:
            return False
        if time.time() < self._trigger_until:
            return True
        return self._detected

    def get_confidence(self) -> float:
        if self.is_person_detected():
            return max(0.75, self._confidence or 0.90)
        return 0.0

    def trigger(self, duration_seconds: float = 4.0) -> None:
        """Trigger a simulated person arrival event."""
        self._trigger_until = time.time() + duration_seconds
        self._confidence = 0.94
        print(f"[Vision] Simulated person arrival triggered for {duration_seconds}s!")

    def set_detected(self, detected: bool, confidence: float = 0.88) -> None:
        self._detected = detected
        self._confidence = confidence if detected else 0.0

    def get_latest_frame(self, target_size: Optional[Tuple[int, int]] = None) -> Optional[Any]:
        """Generate animated synthetic radar surface for Pygame preview."""
        self.sim_tick += 1
        w, h = self.cam_width, self.cam_height

        synth_frame = np.zeros((h, w, 3), dtype=np.uint8)
        synth_frame[:, :] = [14, 22, 28]

        # Optical grid
        synth_frame[::30, :, :] = [30, 48, 62]
        synth_frame[:, ::30, :] = [30, 48, 62]

        is_present = self.is_person_detected()
        px = w // 2 + int(np.sin(self.sim_tick * 0.05) * (w // 4 if is_present else 0))
        py = h // 2

        if is_present:
            y_indices, x_indices = np.ogrid[:h, :w]
            dist = np.sqrt((x_indices - px)**2 + (y_indices - py)**2)
            mask = dist <= 35
            synth_frame[mask] = [52, 211, 153]

        scan_y = int((self.sim_tick * 3) % h)
        synth_frame[scan_y : min(h, scan_y + 2), :, :] = [56, 189, 248]

        try:
            import pygame  # type: ignore
            surface = pygame.image.frombuffer(synth_frame.tobytes(), (w, h), "RGB")
            if is_present:
                rect = pygame.Rect(px - 28, py - 35, 56, 70)
                pygame.draw.rect(surface, (52, 211, 153), rect, width=2)
            if target_size and (target_size[0] != w or target_size[1] != h):
                surface = pygame.transform.smoothscale(surface, target_size)
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
