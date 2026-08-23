"""Finite State Machine (FSM) controlling Portrait lifecycle and transitions."""

import time
from enum import Enum
from typing import Optional, Callable, Dict, Any


class PortraitState(str, Enum):
    IDLE = "IDLE"
    WAKE_PENDING = "WAKE_PENDING"
    GREETING = "GREETING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    COOLDOWN = "COOLDOWN"


class PortraitStateMachine:
    """Manages state transitions, wake-word debouncing, silence counters, and cooldown timeouts."""

    def __init__(self, config: Dict[str, Any], on_state_change: Optional[Callable[[PortraitState], None]] = None):
        self.config = config.get("state_machine", {})
        self.state = PortraitState.IDLE
        self.previous_state = PortraitState.IDLE
        self.on_state_change = on_state_change

        self.consecutive_wake_frames = 0
        self.wake_pending_start_time: Optional[float] = None
        self.silence_count = 0
        self.cooldown_start_time: Optional[float] = None
        self.state_enter_time = time.time()

        # Configuration parameters
        self.wake_confirm_frames = self.config.get("wake_confirm_frames", 3)
        self.wake_confirm_timeout = self.config.get("wake_confirm_timeout_seconds", 1.5)
        self.max_consecutive_silence = self.config.get("max_consecutive_silence", 2)
        self.cooldown_duration = self.config.get("cooldown_duration_seconds", 8.0)

    def transition_to(self, new_state: PortraitState) -> None:
        """Transitions to a new state and triggers callback."""
        if self.state == new_state:
            return

        self.previous_state = self.state
        self.state = new_state
        self.state_enter_time = time.time()

        print(f"[State Machine] Transition: {self.previous_state.value} -> {self.state.value}")

        if self.on_state_change:
            try:
                self.on_state_change(new_state)
            except Exception as e:
                print(f"[State Machine] Error in on_state_change callback: {e}")

    def on_person_frame(self, detected: bool) -> None:
        """Process an optical frame detection event."""
        if self.state == PortraitState.IDLE:
            if detected:
                self.consecutive_wake_frames += 1
                if self.consecutive_wake_frames >= self.wake_confirm_frames:
                    self.consecutive_wake_frames = 0
                    self.wake_pending_start_time = time.time()
                    self.transition_to(PortraitState.WAKE_PENDING)
            else:
                self.consecutive_wake_frames = 0

        elif self.state == PortraitState.WAKE_PENDING:
            if detected:
                # Confirmed presence -> proceed to GREETING
                self.wake_pending_start_time = None
                self.silence_count = 0
                self.transition_to(PortraitState.GREETING)
            else:
                # False positive check with timeout
                if self.wake_pending_start_time and (time.time() - self.wake_pending_start_time > self.wake_confirm_timeout):
                    print("[State Machine] Wake confirmation timed out (false trigger). Returning to IDLE.")
                    self.wake_pending_start_time = None
                    self.transition_to(PortraitState.IDLE)

    def on_greeting_complete(self) -> None:
        """Called when initial greeting audio playback finishes."""
        if self.state == PortraitState.GREETING:
            self.transition_to(PortraitState.LISTENING)

    def on_speech_detected(self) -> None:
        """Called when user starts uttering speech."""
        if self.state == PortraitState.LISTENING:
            self.silence_count = 0
            self.transition_to(PortraitState.THINKING)

    def on_speech_silence(self) -> None:
        """Called when listening interval times out with no user speech."""
        if self.state == PortraitState.LISTENING:
            self.silence_count += 1
            print(f"[State Machine] Silence turn {self.silence_count}/{self.max_consecutive_silence}")

            if self.silence_count >= self.max_consecutive_silence:
                print("[State Machine] Max silence reached. Transitioning to COOLDOWN.")
                self.start_cooldown()
            else:
                # Prompt the user or retry listening
                self.transition_to(PortraitState.LISTENING)

    def on_llm_response_ready(self) -> None:
        """Called when LLM generation is ready to be spoken."""
        if self.state == PortraitState.THINKING:
            self.transition_to(PortraitState.SPEAKING)

    def on_speaking_complete(self) -> None:
        """Called when response audio finishes playback."""
        if self.state == PortraitState.SPEAKING:
            self.transition_to(PortraitState.LISTENING)

    def start_cooldown(self) -> None:
        """Enters cooldown to prevent instant re-triggering."""
        self.cooldown_start_time = time.time()
        self.transition_to(PortraitState.COOLDOWN)

    def update(self) -> None:
        """Periodic tick to evaluate timeouts."""
        now = time.time()

        if self.state == PortraitState.COOLDOWN:
            if self.cooldown_start_time and (now - self.cooldown_start_time >= self.cooldown_duration):
                self.cooldown_start_time = None
                self.silence_count = 0
                self.transition_to(PortraitState.IDLE)
