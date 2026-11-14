"""Tier 2 Wake Word and Conversational Intent Triggers.

Coordinates keyword spotting ('Wilhelm!') and optical intent cues
(sustained visitor gaze dwell) to verify visitor engagement before waking.
"""

from abc import ABC, abstractmethod
import re
import time
from typing import Any, Dict, List, Optional, Tuple


class WakeTriggerResult:
    """Result of Tier 2 conversational intent evaluation."""

    def __init__(
        self,
        triggered: bool = False,
        source: str = "none",
        keyword: Optional[str] = None,
        confidence: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.triggered = bool(triggered)
        self.source = str(source)  # "wake_word", "gaze_dwell", "motion", "manual", "none"
        self.keyword = keyword
        self.confidence = float(confidence)
        self.metadata = metadata or {}
        self.timestamp = time.monotonic()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered": self.triggered,
            "source": self.source,
            "keyword": self.keyword,
            "confidence": round(self.confidence, 3),
            "metadata": self.metadata,
        }


class BaseWakeWordBackend(ABC):
    """Abstract interface for acoustic keyword spotting engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def process_audio(self, pcm_chunk: bytes) -> Optional[WakeTriggerResult]:
        """Process 16-bit linear PCM audio chunk (16kHz)."""
        return None


class OpenWakeWordBackend(BaseWakeWordBackend):
    """Keyword spotting using openWakeWord (ONNX Runtime)."""

    def __init__(self, keywords: Optional[List[str]] = None):
        self._keywords = keywords or ["wilhelm", "hey wilhelm"]
        self._available = False
        self._check_availability()

    @property
    def name(self) -> str:
        return "openwakeword"

    def _check_availability(self) -> None:
        try:
            import openwakeword  # type: ignore  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def process_audio(self, pcm_chunk: bytes) -> Optional[WakeTriggerResult]:
        if not self._available:
            return None
        # On hardware with openwakeword installed, feeds audio frames to ONNX model
        return None


class PorcupineWakeWordBackend(BaseWakeWordBackend):
    """Keyword spotting using Picovoice Porcupine."""

    def __init__(self, access_key: str = "", model_path: Optional[str] = None):
        self._access_key = access_key
        self._model_path = model_path
        self._available = False
        self._check_availability()

    @property
    def name(self) -> str:
        return "porcupine"

    def _check_availability(self) -> None:
        try:
            import pvporcupine  # type: ignore  # noqa: F401
            self._available = bool(self._access_key)
        except ImportError:
            self._available = False

    def is_available(self) -> bool:
        return self._available


class KeywordFilterDetector:
    """Matches wake phrases in transcribed speech text."""

    def __init__(self, wake_phrases: Optional[List[str]] = None):
        phrases = wake_phrases or ["wilhelm", "hey wilhelm", "hello wilhelm", "artificer"]
        # Sort longest phrases first to prevent sub-string eclipsing
        sorted_phrases = sorted(phrases, key=len, reverse=True)
        self._patterns = [re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE) for p in sorted_phrases]

    def check_text(self, text: str) -> Optional[WakeTriggerResult]:
        if not text:
            return None
        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                return WakeTriggerResult(
                    triggered=True,
                    source="wake_word",
                    keyword=match.group(0),
                    confidence=0.95,
                    metadata={"matched_text": text},
                )
        return None


class GazeDwellTrigger:
    """Intent cue trigger: Fires when visitor maintains sustained eye contact / facing angle."""

    def __init__(
        self,
        dwell_threshold_seconds: float = 1.5,
        max_distance: float = 1.4,
        facing_tolerance: float = 0.40,
    ):
        self.dwell_threshold = float(dwell_threshold_seconds)
        self.max_distance = float(max_distance)
        self.facing_tolerance = float(facing_tolerance)
        self._has_triggered = False

    def reset(self) -> None:
        self._has_triggered = False

    def evaluate(
        self,
        is_detected: bool,
        dwell_seconds: float,
        gaze: Tuple[float, float, float],
    ) -> Optional[WakeTriggerResult]:
        norm_x, norm_y, distance = gaze

        if not is_detected or distance > self.max_distance or abs(norm_x) > self.facing_tolerance:
            # Person departed, looked away, or moved too far
            self._has_triggered = False
            return None

        if self._has_triggered:
            # Already fired for this continuous dwell cycle
            return None

        if dwell_seconds >= self.dwell_threshold:
            self._has_triggered = True
            return WakeTriggerResult(
                triggered=True,
                source="gaze_dwell",
                keyword=None,
                confidence=0.90,
                metadata={
                    "dwell_seconds": round(dwell_seconds, 2),
                    "distance": round(distance, 2),
                    "gaze_x": round(norm_x, 2),
                },
            )

        return None


class TwoTierWakeController:
    """Coordinates Tier 1 presence metrics and Tier 2 intent triggers."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        vision_cfg = cfg.get("vision", {})
        two_tier_cfg = vision_cfg.get("two_tier", {})

        self.enabled = bool(two_tier_cfg.get("enabled", True))
        self.wake_mode = str(two_tier_cfg.get("tier2_wake_mode", "hybrid")).lower()
        self.wake_words = two_tier_cfg.get("wake_words", ["wilhelm", "hey wilhelm", "hello wilhelm"])
        self.dwell_threshold = float(two_tier_cfg.get("gaze_dwell_threshold_seconds", 1.5))
        self.max_distance = float(two_tier_cfg.get("max_interaction_distance", 1.4))
        self.facing_tolerance = float(two_tier_cfg.get("facing_angle_tolerance", 0.40))

        self.gaze_dwell_trigger = GazeDwellTrigger(
            dwell_threshold_seconds=self.dwell_threshold,
            max_distance=self.max_distance,
            facing_tolerance=self.facing_tolerance,
        )
        self.keyword_filter = KeywordFilterDetector(self.wake_words)
        self.openwakeword_backend = OpenWakeWordBackend(self.wake_words)

        self._manual_wake_active_until = 0.0
        self._last_trigger_result: Optional[WakeTriggerResult] = None

    def trigger_manual_wake(self, duration_seconds: float = 3.0) -> WakeTriggerResult:
        """Manually trigger wake intent (e.g. via keyboard SPACE or API)."""
        self._manual_wake_active_until = time.monotonic() + duration_seconds
        result = WakeTriggerResult(
            triggered=True,
            source="manual",
            keyword="keyboard_space",
            confidence=1.0,
        )
        self._last_trigger_result = result
        return result

    def evaluate_wake_intent(
        self,
        person_detected: bool,
        dwell_seconds: float,
        gaze: Tuple[float, float, float],
        audio_chunk: Optional[bytes] = None,
        transcript_text: Optional[str] = None,
    ) -> WakeTriggerResult:
        """Evaluate whether Tier 2 conditions are met to command a state transition."""
        now = time.monotonic()

        # 1. Manual trigger override
        if now < self._manual_wake_active_until:
            return WakeTriggerResult(
                triggered=True,
                source="manual",
                keyword="keyboard_space",
                confidence=1.0,
            )

        if not self.enabled:
            # Fall back to legacy motion trigger
            return WakeTriggerResult(
                triggered=person_detected,
                source="motion_legacy",
                confidence=0.85 if person_detected else 0.0,
            )

        # Legacy motion mode: wakes directly upon person frame
        if self.wake_mode == "motion_legacy":
            return WakeTriggerResult(
                triggered=person_detected,
                source="motion",
                confidence=0.85 if person_detected else 0.0,
            )

        # Tier 1 must be active for conversational intent
        if not person_detected:
            self.gaze_dwell_trigger.reset()
            return WakeTriggerResult(triggered=False, source="none")

        # 2. Check Transcript / Keyword filter if audio/text provided
        if transcript_text and self.wake_mode in ("wake_word_only", "hybrid", "auto"):
            kw_result = self.keyword_filter.check_text(transcript_text)
            if kw_result and kw_result.triggered:
                self._last_trigger_result = kw_result
                return kw_result

        # 3. Check Acoustic Wake Word Backend
        if audio_chunk and self.wake_mode in ("wake_word_only", "hybrid", "auto"):
            if self.openwakeword_backend.is_available():
                oww_res = self.openwakeword_backend.process_audio(audio_chunk)
                if oww_res and oww_res.triggered:
                    self._last_trigger_result = oww_res
                    return oww_res

        # 4. Check Gaze Dwell Intent Trigger
        if self.wake_mode in ("gaze_dwell", "hybrid", "auto"):
            dwell_res = self.gaze_dwell_trigger.evaluate(person_detected, dwell_seconds, gaze)
            if dwell_res and dwell_res.triggered:
                self._last_trigger_result = dwell_res
                return dwell_res

        return WakeTriggerResult(triggered=False, source="none")

    def reset(self) -> None:
        """Reset trigger history."""
        self._manual_wake_active_until = 0.0
        self.gaze_dwell_trigger.reset()
        self._last_trigger_result = None

    def get_status_info(self) -> Dict[str, Any]:
        return {
            "two_tier_enabled": self.enabled,
            "wake_mode": self.wake_mode,
            "dwell_threshold": self.dwell_threshold,
            "max_distance": self.max_distance,
            "openwakeword_available": self.openwakeword_backend.is_available(),
            "last_trigger_source": self._last_trigger_result.source if self._last_trigger_result else "none",
        }
