"""Keyboard / simulated STT driver for desktop demo mode."""

import queue
import time
from typing import Optional, Dict, Any
from stt.base import BaseSTT


class KeyboardSTT(BaseSTT):
    """Allows queuing simulated utterances from keyboard hotkeys ('t' in Pygame or CLI input)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.input_queue: queue.Queue = queue.Queue()
        self.sample_phrases = [
            "Good day, sir knight! What is the password?",
            "Who goes there?",
            "Can you tell me where the Gryffindor common room is?",
            "What monsters have you fought lately?",
            "Farewell for now, Lord Cadogan.",
        ]
        self._sample_index = 0

    def inject_text(self, text: str) -> None:
        """Inject a spoken phrase into the transcription queue."""
        print(f"[STT] Injected phrase: \"{text}\"")
        self.input_queue.put(text)

    def inject_next_sample(self) -> str:
        """Inject the next pre-scripted sample phrase."""
        phrase = self.sample_phrases[self._sample_index % len(self.sample_phrases)]
        self._sample_index += 1
        self.inject_text(phrase)
        return phrase

    def listen_and_transcribe(self, timeout_seconds: float = 2.0, max_duration_seconds: float = 10.0) -> Optional[str]:
        try:
            # Wait for text to be queued with timeout
            text = self.input_queue.get(timeout=timeout_seconds)
            return text
        except queue.Empty:
            return None
