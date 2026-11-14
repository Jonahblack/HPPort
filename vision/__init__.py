"""Vision perception, person detection, and two-tier engagement package."""

from vision.base import BaseVisionDetector
from vision.hailo import HailoVision
from vision.mock import MockVision
from vision.person_detector import (
    DetectionResult,
    BasePersonDetectorBackend,
    HailoPersonDetectorBackend,
    OpenCVPersonDetectorBackend,
    MotionDetectorBackend,
    SmartPersonDetector,
)
from vision.wake_word import (
    WakeTriggerResult,
    BaseWakeWordBackend,
    OpenWakeWordBackend,
    PorcupineWakeWordBackend,
    KeywordFilterDetector,
    GazeDwellTrigger,
    TwoTierWakeController,
)

__all__ = [
    "BaseVisionDetector",
    "HailoVision",
    "MockVision",
    "DetectionResult",
    "BasePersonDetectorBackend",
    "HailoPersonDetectorBackend",
    "OpenCVPersonDetectorBackend",
    "MotionDetectorBackend",
    "SmartPersonDetector",
    "WakeTriggerResult",
    "BaseWakeWordBackend",
    "OpenWakeWordBackend",
    "PorcupineWakeWordBackend",
    "KeywordFilterDetector",
    "GazeDwellTrigger",
    "TwoTierWakeController",
]
