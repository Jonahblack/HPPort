"""Unit tests for Portrait State Machine."""

import unittest
import time
from copy import deepcopy
from config import DEFAULT_CONFIG
from state_machine import PortraitStateMachine, PortraitState


class TestPortraitStateMachine(unittest.TestCase):

    def setUp(self):
        self.config = deepcopy(DEFAULT_CONFIG)
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

    def test_speech_detected_during_cooldown_triggers_thinking(self):
        self.fsm.start_cooldown()
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.fsm.on_speech_detected()
        self.assertEqual(self.fsm.state, PortraitState.THINKING)

    def test_cooldown_presence_latching_prevents_immediate_rewake(self):
        self.fsm.start_cooldown()
        self.assertTrue(self.fsm._cooldown_presence_latched)

        # Person still standing there during cooldown
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)

        # Cooldown expires
        time.sleep(0.55)
        self.fsm.update()
        self.assertEqual(self.fsm.state, PortraitState.IDLE)
        self.assertTrue(self.fsm._cooldown_presence_latched)

        # Lingering visitor continues to be detected - MUST NOT wake
        for _ in range(5):
            self.fsm.on_person_frame(True)
            self.assertEqual(self.fsm.state, PortraitState.IDLE)

        # Visitor leaves frame
        self.fsm.on_person_frame(False)
        self.assertFalse(self.fsm._cooldown_presence_latched)

        # New visitor arrives: debouncing works normally
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

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

    def test_elapsed_cooldown_waits_for_physical_action(self):
        self.fsm.start_cooldown()
        self.fsm.cooldown_start_time -= 10
        self.fsm.update(visual_ready=False)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.fsm.update(visual_ready=True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)


if __name__ == "__main__":
    unittest.main()
