"""
Finite State Machine for the Talking Portrait.
Coordinates system lifecycle transitions between IDLE, WAKE_PENDING, GREETING,
LISTENING, THINKING, SPEAKING, and COOLDOWN.
"""

from enum import Enum, auto
import logging
import time
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()
    WAKE_PENDING = auto()
    GREETING = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    COOLDOWN = auto()


class StateMachine:
    """Explicit state machine managing lifecycle states and transition events."""

    def __init__(
        self,
        wake_confirm_frames: int = 3,
        wake_confirm_timeout_seconds: float = 1.5,
        cooldown_duration_seconds: float = 8.0,
        max_silence_turns: int = 2,
    ):
        self.state: State = State.IDLE
        self.wake_confirm_frames: int = wake_confirm_frames
        self.wake_confirm_timeout_seconds: float = wake_confirm_timeout_seconds
        self.cooldown_duration_seconds: float = cooldown_duration_seconds
        self.max_silence_turns: int = max_silence_turns

        self.consecutive_detections: int = 0
        self.wake_pending_start_time: float = 0.0
        self.cooldown_start_time: float = 0.0
        self.silence_count: int = 0
        self.state_enter_time: float = time.time()

        self._callbacks: Dict[State, List[Callable[[State], None]]] = {s: [] for s in State}

    def register_on_enter(self, state: State, callback: Callable[[State], None]) -> None:
        """Register a callback to run when entering a specific state."""
        self._callbacks[state].append(callback)

    def transition_to(self, new_state: State, reason: str = "") -> None:
        """Explicitly transition to a new state and fire callbacks."""
        old_state = self.state
        if old_state == new_state:
            return

        self.state = new_state
        self.state_enter_time = time.time()
        logger.info("FSM Transition: %s -> %s %s", old_state.name, new_state.name, f"({reason})" if reason else "")

        if new_state == State.IDLE:
            self.consecutive_detections = 0
            self.silence_count = 0
        elif new_state == State.WAKE_PENDING:
            self.wake_pending_start_time = time.time()
            self.consecutive_detections = 1
        elif new_state == State.COOLDOWN:
            self.cooldown_start_time = time.time()

        for cb in self._callbacks.get(new_state, []):
            try:
                cb(old_state)
            except Exception as e:
                logger.error("Error executing on_enter callback for %s: %s", new_state.name, e)

    def on_person_detected(self) -> None:
        """Called when a vision detection frame detects a person."""
        now = time.time()

        if self.state == State.IDLE:
            self.transition_to(State.WAKE_PENDING, reason="Initial person detection frame")
        elif self.state == State.WAKE_PENDING:
            self.consecutive_detections += 1
            if self.consecutive_detections >= self.wake_confirm_frames:
                self.transition_to(State.GREETING, reason=f"Confirmed {self.consecutive_detections} frames")

    def update(self) -> None:
        """Periodic tick to evaluate time-based state timeouts."""
        now = time.time()

        if self.state == State.WAKE_PENDING:
            if now - self.wake_pending_start_time > self.wake_confirm_timeout_seconds:
                # Timed out without confirming required consecutive frames
                logger.info("Wake confirmation timed out; returning to IDLE.")
                self.transition_to(State.IDLE, reason="Wake timeout / false positive")

        elif self.state == State.COOLDOWN:
            if now - self.cooldown_start_time >= self.cooldown_duration_seconds:
                self.transition_to(State.IDLE, reason="Cooldown period expired")

    def on_greeting_finished(self) -> None:
        """Triggered after greeting audio finishes playing."""
        if self.state == State.GREETING:
            self.transition_to(State.LISTENING, reason="Greeting playback finished")

    def on_speech_received(self, text: str) -> None:
        """Triggered when STT captures user speech."""
        if self.state == State.LISTENING:
            self.silence_count = 0
            self.transition_to(State.THINKING, reason=f"Received user speech: '{text}'")

    def on_silence_timeout(self) -> None:
        """Triggered when listening expires without speech."""
        if self.state == State.LISTENING:
            self.silence_count += 1
            logger.info("Listening silence count: %d/%d", self.silence_count, self.max_silence_turns)
            if self.silence_count >= self.max_silence_turns:
                self.transition_to(State.COOLDOWN, reason="Max consecutive silences reached")
            else:
                # Re-prompt or continue listening
                self.transition_to(State.LISTENING, reason="Silence prompt retry")

    def on_llm_response_ready(self) -> None:
        """Triggered when LLM response is ready for TTS."""
        if self.state == State.THINKING:
            self.transition_to(State.SPEAKING, reason="LLM response generated")

    def on_speech_playback_finished(self) -> None:
        """Triggered when Piper audio finishes playing."""
        if self.state == State.SPEAKING:
            self.transition_to(State.LISTENING, reason="Portrait finished speaking")

    def on_conversation_ended(self, reason: str = "Explicit farewell") -> None:
        """End active conversation and enter cooldown."""
        self.transition_to(State.COOLDOWN, reason=reason)
