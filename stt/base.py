"""
Base abstract interface for Speech-to-Text (STT) engines.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class STTResult:
    text: str
    duration_seconds: float = 0.0
    confidence: float = 1.0


class BaseSTT(ABC):
    """Abstract interface for STT engines."""

    @abstractmethod
    def start_listening(self, callback: Callable[[STTResult], None], on_silence: Optional[Callable[[], None]] = None) -> None:
        """Start listening asynchronously on microphone input."""
        pass

    @abstractmethod
    def stop_listening(self) -> None:
        """Stop listening."""
        pass

    @abstractmethod
    def is_listening(self) -> bool:
        """Return listening status."""
        pass

    @abstractmethod
    def transcribe_file(self, audio_path: str) -> STTResult:
        """Transcribe an existing audio file synchronously."""
        pass
