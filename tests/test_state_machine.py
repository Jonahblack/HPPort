"""
Unit tests for the Talking Portrait State Machine.
"""

import time
import unittest
from state_machine import State, StateMachine


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.fsm = StateMachine(
            wake_confirm_frames=3,
            wake_confirm_timeout_seconds=0.5,
            cooldown_duration_seconds=0.5,
            max_silence_turns=2,
        )

    def test_initial_state_idle(self):
        self.assertEqual(self.fsm.state, State.IDLE)

    def test_wake_confirmation_success(self):
        self.fsm.on_person_detected()
        self.assertEqual(self.fsm.state, State.WAKE_PENDING)

        self.fsm.on_person_detected()
        self.assertEqual(self.fsm.state, State.WAKE_PENDING)

        self.fsm.on_person_detected()
        self.assertEqual(self.fsm.state, State.GREETING)

    def test_wake_timeout_to_idle(self):
        self.fsm.on_person_detected()
        self.assertEqual(self.fsm.state, State.WAKE_PENDING)
        time.sleep(0.6)
        self.fsm.update()
        self.assertEqual(self.fsm.state, State.IDLE)

    def test_conversation_cycle(self):
        # Reach GREETING
        self.fsm.transition_to(State.GREETING)
        self.fsm.on_greeting_finished()
        self.assertEqual(self.fsm.state, State.LISTENING)

        # Receive speech
        self.fsm.on_speech_received("Hello Lord Cadogan!")
        self.assertEqual(self.fsm.state, State.THINKING)

        # LLM response ready
        self.fsm.on_llm_response_ready()
        self.assertEqual(self.fsm.state, State.SPEAKING)

        # Speaking finished returns to listening
        self.fsm.on_speech_playback_finished()
        self.assertEqual(self.fsm.state, State.LISTENING)

    def test_silence_threshold_to_cooldown(self):
        self.fsm.transition_to(State.LISTENING)
        self.fsm.on_silence_timeout()
        self.assertEqual(self.fsm.state, State.LISTENING)

        self.fsm.on_silence_timeout()
        self.assertEqual(self.fsm.state, State.COOLDOWN)

        time.sleep(0.6)
        self.fsm.update()
        self.assertEqual(self.fsm.state, State.IDLE)


if __name__ == "__main__":
    unittest.main()
