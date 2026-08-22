"""
Keyboard-based STT for desktop development and debugging.
Allows direct text input to simulate spoken dialogue without hardware microphone.
"""

import logging
import queue
import threading
from typing import Callable, Optional

from .base import BaseSTT, STTResult

logger = logging.getLogger(__name__)


class KeyboardSTT(BaseSTT):
    """STT simulator allowing interactive text injection via queue or prompt."""

    def __init__(self):
        self._is_listening = False
        self._callback: Optional[Callable[[STTResult], None]] = None
        self._silence_callback: Optional[Callable[[], None]] = None
        self._input_queue: queue.Queue = queue.Queue()

    def is_listening(self) -> bool:
        return self._is_listening

    def start_listening(self, callback: Callable[[STTResult], None], on_silence: Optional[Callable[[], None]] = None) -> None:
        self._is_listening = True
        self._callback = callback
        self._silence_callback = on_silence
        logger.info("KeyboardSTT listening. Use inject_text() or CLI to provide user dialogue.")

    def stop_listening(self) -> None:
        self._is_listening = False
        logger.info("KeyboardSTT stopped listening.")

    def inject_text(self, text: str) -> None:
        """Programmatically inject user utterance (e.g. from desktop UI or test)."""
        if self._is_listening and self._callback:
            logger.info("KeyboardSTT injected: '%s'", text)
            self._callback(STTResult(text=text, duration_seconds=0.1))

    def trigger_silence(self) -> None:
        """Trigger silence timeout simulation."""
        if self._is_listening and self._silence_callback:
            logger.info("KeyboardSTT triggered silence timeout.")
            self._silence_callback()

    def transcribe_file(self, audio_path: str) -> STTResult:
        return STTResult(text="Desktop injected keyboard audio", duration_seconds=0.05)
