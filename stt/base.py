"""Abstract base class for Speech-To-Text (STT) audio input."""

from abc import ABC, abstractmethod
from typing import Optional


class BaseSTT(ABC):
    """Interface for listening to microphone and transcribing user speech."""

    @abstractmethod
    def listen_and_transcribe(self, timeout_seconds: float = 2.0, max_duration_seconds: float = 10.0) -> Optional[str]:
        """Record audio until silence is detected and transcribe to text string.

        Args:
            timeout_seconds: Duration of initial silence before giving up.
            max_duration_seconds: Hard ceiling for total utterance recording.

        Returns:
            Transcribed text, or None if silence/timeout occurred.
        """
        pass
