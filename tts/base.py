"""Abstract base class for Text-To-Speech (TTS) audio generation."""

from abc import ABC, abstractmethod
from typing import Tuple, Optional


class BaseTTS(ABC):
    """Interface for synthesizing spoken audio files from dialogue text."""

    @abstractmethod
    def synthesize_to_file(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        """Synthesize text to a WAV audio file.

        Args:
            text: Dialogue string to speak.
            output_wav_path: Destination path for generated 16-bit WAV file.

        Returns:
            Tuple of (output_wav_path, duration_in_seconds).
        """
        pass
