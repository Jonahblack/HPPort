"""
Base abstract interface for Vision and Person Detection modules.
Supports Hailo AI HAT on Raspberry Pi 5 and mock vision for desktop testing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass
class DetectionFrame:
    person_detected: bool
    confidence: float = 0.0
    bounding_box: Optional[Tuple[float, float, float, float]] = None  # (x, y, w, h) normalized
    timestamp: float = 0.0


class BaseVisionDetector(ABC):
    """Abstract interface for person detection backends."""

    @abstractmethod
    def start(self, callback: Callable[[DetectionFrame], None]) -> None:
        """Start capturing camera frames and running person detection asynchronously."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop vision capture and release camera/hailo hardware resources."""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """Check if detector is currently capturing."""
        pass

    @abstractmethod
    def get_last_detection(self) -> DetectionFrame:
        """Return the most recent detection result."""
        pass
