"""Unit tests for Portrait State Machine."""

import unittest
from config import DEFAULT_CONFIG
from state_machine import PortraitStateMachine, PortraitState


class TestPortraitStateMachine(unittest.TestCase):

    def setUp(self):
        self.config = dict(DEFAULT_CONFIG)
        self.config["state_machine"]["wake_confirm_frames"] = 2
        self.config["state_machine"]["cooldown_duration_seconds"] = 0.5
        self.fsm = PortraitStateMachine(self.config)

    def test_initial_state_is_idle(self):
        self.assertEqual(self.fsm.state, PortraitState.IDLE)

    def test_wake_debouncing(self):
        # 1 frame detected -> still IDLE
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)

        # 2nd frame detected -> transitions to WAKE_PENDING
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

        # Confirmed presence -> GREETING
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.GREETING)

    def test_greeting_to_listening(self):
        self.fsm.state = PortraitState.GREETING
        self.fsm.on_greeting_complete()
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)

    def test_speech_detected_to_thinking(self):
        self.fsm.state = PortraitState.LISTENING
        self.fsm.on_speech_detected()
        self.assertEqual(self.fsm.state, PortraitState.THINKING)

    def test_llm_ready_to_speaking(self):
        self.fsm.state = PortraitState.THINKING
        self.fsm.on_llm_response_ready()
        self.assertEqual(self.fsm.state, PortraitState.SPEAKING)

    def test_speaking_complete_returns_to_listening(self):
        self.fsm.state = PortraitState.SPEAKING
        self.fsm.on_speaking_complete()
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)

    def test_max_silence_enters_cooldown(self):
        self.fsm.state = PortraitState.LISTENING
        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)
        self.assertEqual(self.fsm.silence_count, 1)

        # Second silence triggers cooldown
        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)


if __name__ == "__main__":
    unittest.main()
