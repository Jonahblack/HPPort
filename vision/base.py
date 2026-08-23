"""Abstract base class for vision / optical person detection drivers."""

from abc import ABC, abstractmethod


class BaseVisionDetector(ABC):
    """Interface for optical detection sensors (Hailo-8L, USB Webcam, Mock)."""

    @abstractmethod
    def start(self) -> None:
        """Initialize camera capture and NPU pipeline."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Release camera and NPU resources."""
        pass

    @abstractmethod
    def is_person_detected(self) -> bool:
        """Poll whether a person is present in the current camera frame."""
        pass

    @abstractmethod
    def get_confidence(self) -> float:
        """Get latest detection confidence score (0.0 to 1.0)."""
        pass
