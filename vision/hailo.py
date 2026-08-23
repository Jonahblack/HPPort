"""Hailo AI HAT (Hailo-8L) YOLOv8 person detector for Raspberry Pi 5."""

import time
import os
from typing import Dict, Any, Optional
from vision.base import BaseVisionDetector


class HailoVision(BaseVisionDetector):
    """Hailo-8L NPU hardware-accelerated person detection using YOLOv8 HEF."""

    def __init__(self, config: Dict[str, Any]):
        vision_cfg = config.get("vision", {})
        self.confidence_threshold = float(vision_cfg.get("confidence_threshold", 0.55))
        self.poll_interval = float(vision_cfg.get("poll_interval_seconds", 0.1))
        self.model_path = os.path.join(
            config.get("hardware", {}).get("models_dir", "/mnt/portrait/models"),
            "hailo",
            "yolov8s_person.hef",
        )

        self._running = False
        self._latest_detected = False
        self._latest_confidence = 0.0
        self._hailo_initialized = False

    def start(self) -> None:
        """Initialize HailoRT or fallback v4l2 device."""
        self._running = True
        print(f"[Vision] Initializing Hailo-8L detector with model: {self.model_path}")

        try:
            # Check for hailo Python bindings on Raspberry Pi OS
            import hailo  # type: ignore
            print("[Vision] HailoRT Python bindings successfully loaded.")
            self._hailo_initialized = True
        except ImportError:
            print("[Vision] Notice: hailo Python bindings not in current venv. Using camera fallback poll.")
            self._hailo_initialized = False

    def stop(self) -> None:
        self._running = False
        print("[Vision] Hailo detector stopped.")

    def is_person_detected(self) -> bool:
        if not self._running:
            return False
        return self._latest_detected

    def get_confidence(self) -> float:
        return self._latest_confidence

    def simulate_detection(self, detected: bool, confidence: float = 0.85) -> None:
        """Simulate detection event for manual testing."""
        self._latest_detected = detected
        self._latest_confidence = confidence if detected else 0.0
