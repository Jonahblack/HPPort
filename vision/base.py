"""Abstract base class for optical presence-trigger drivers."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, List


class BaseVisionDetector(ABC):
    """Interface for camera motion and simulated presence triggers."""

    @abstractmethod
    def start(self) -> None:
        """Initialize the camera or simulated input pipeline."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Release input resources."""
        pass

    @abstractmethod
    def is_person_detected(self) -> bool:
        """Poll the legacy presence flag (currently driven by motion)."""
        pass

    @abstractmethod
    def get_confidence(self) -> float:
        """Get latest detection confidence score (0.0 to 1.0)."""
        pass

    def get_latest_frame(self, target_size: Optional[Tuple[int, int]] = None) -> Optional[Any]:
        """Get the latest camera frame as a surface or array for corner PiP feed."""
        return None

    def get_status_info(self) -> Dict[str, Any]:
        """Get hardware diagnostic information."""
        return {
            "driver": "unknown",
            "active": False,
            "fps": 0.0,
            "detected": False,
            "confidence": 0.0,
        }

    def get_visitor_gaze(self) -> Tuple[float, float, float]:
        """Get normalized gaze target (x, y, distance) where x, y are in [-1.0, 1.0] and distance >= 0.0."""
        return (0.0, 0.0, 1.0)

    def is_person_present(self) -> bool:
        """Tier 1: Check if a human person is identified in the field of view."""
        return self.is_person_detected()

    def is_visitor_engaged(self) -> bool:
        """Tier 1: Check if person is in the close conversational interaction zone."""
        return self.is_person_detected()

    def get_visitor_proximity(self) -> float:
        """Get estimated normalized distance to the primary visitor (1.0 = standard conversational distance)."""
        _, _, dist = self.get_visitor_gaze()
        return dist

    def get_person_detections(self) -> List[Dict[str, Any]]:
        """Get list of bounding boxes and confidence scores for detected persons."""
        return []

    def get_presence_metrics(self) -> Dict[str, Any]:
        """Get detailed presence metrics including dwell time, distance, and facing confidence."""
        return {
            "present": self.is_person_present(),
            "engaged": self.is_visitor_engaged(),
            "confidence": self.get_confidence(),
            "proximity": self.get_visitor_proximity(),
            "dwell_seconds": 0.0,
            "gaze": self.get_visitor_gaze(),
        }
