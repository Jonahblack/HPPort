"""
Base abstract interface for Text-to-Speech (TTS) engines.
Includes audio synthesis, streaming chunk playback, and amplitude calculation for lip-sync.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Generator, List, Optional


@dataclass
class TTSMetrics:
    generation_time_seconds: float = 0.0
    time_to_first_audio_seconds: float = 0.0
    audio_duration_seconds: float = 0.0


@dataclass
class TTSAudioResult:
    audio_path: Optional[str]
    raw_pcm: Optional[bytes]
    sample_rate: int = 22050
    amplitudes: List[float] = None
    metrics: TTSMetrics = None


class BaseTTS(ABC):
    """Abstract interface for TTS engines."""

    @abstractmethod
    def synthesize(self, text: str, output_path: Optional[str] = None) -> TTSAudioResult:
        """Synthesize text into audio and return audio result with amplitude profile."""
        pass

    @abstractmethod
    def play_audio(
        self,
        audio_result: TTSAudioResult,
        amplitude_callback: Optional[Callable[[float], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        """Play synthesized audio and continuously dispatch amplitude levels for mouth flapping."""
        pass

    @abstractmethod
    def stop_playback(self) -> None:
        """Stop current audio playback immediately."""
        pass
