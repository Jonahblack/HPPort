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

    def test_presence_loss_during_listening_triggers_cooldown_early(self):
        self.fsm.state = PortraitState.LISTENING
        self.fsm.presence_loss_frames = 3

        # 2 frames of absence -> still LISTENING
        self.fsm.on_person_frame(False)
        self.fsm.on_person_frame(False)
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)

        # 3rd frame of absence -> triggers COOLDOWN early
        self.fsm.on_person_frame(False)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.assertTrue(self.fsm._presence_lost)
        # Latched presence should be False so a new visitor can wake immediately
        self.assertFalse(self.fsm._cooldown_presence_latched)

    def test_presence_loss_accelerates_cooldown_duration(self):
        self.fsm.presence_loss_cooldown_duration = 0.2
        self.fsm.cooldown_duration = 10.0
        self.fsm.start_cooldown(presence_lost=True)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.assertTrue(self.fsm._presence_lost)

        # Before accelerated duration expires
        self.fsm.update(visual_ready=True)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)

        # After accelerated duration (0.2s)
        time.sleep(0.25)
        self.fsm.update(visual_ready=True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)
        self.assertFalse(self.fsm._presence_lost)

    def test_fast_wake_during_cooldown_for_new_visitor(self):
        self.fsm.wake_confirm_frames = 2
        # Visitor walked away, cooldown started with presence lost
        self.fsm.start_cooldown(presence_lost=True)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.assertFalse(self.fsm._cooldown_presence_latched)

        # New visitor approaches during cooldown
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)

        # Second confirmed frame -> fast interrupt to WAKE_PENDING!
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

    def test_presence_loss_during_cooldown_unlatches_and_accelerates(self):
        self.fsm.presence_loss_frames = 3
        self.fsm.presence_loss_cooldown_duration = 0.1
        self.fsm.start_cooldown(presence_lost=False)
        self.assertTrue(self.fsm._cooldown_presence_latched)

        # Visitor departs during cooldown
        self.fsm.on_person_frame(False)
        self.assertFalse(self.fsm._cooldown_presence_latched)

        self.fsm.on_person_frame(False)
        self.fsm.on_person_frame(False)
        self.assertTrue(self.fsm._presence_lost)

        time.sleep(0.15)
        self.fsm.update(visual_ready=True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)

    def test_wake_pending_rapid_departure_before_timeout_retains_wake_pending(self):
        # 2 frames to reach WAKE_PENDING
        self.fsm.on_person_frame(True)
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

        # Immediate absence frame within timeout (e.g. momentary occlusion)
        self.fsm.on_person_frame(False)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)
        self.assertEqual(self.fsm.consecutive_absence_frames, 1)

    def test_wake_pending_departure_after_timeout_returns_to_idle(self):
        self.fsm.wake_confirm_timeout = 0.1
        self.fsm.on_person_frame(True)
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

        # Timeout passes while visitor has departed
        time.sleep(0.15)
        self.fsm.on_person_frame(False)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)
        self.assertIsNone(self.fsm.wake_pending_start_time)

    def test_wake_pending_re_arrival_resets_and_proceeds_to_greeting(self):
        self.fsm.on_person_frame(True)
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

        # Brief absence
        self.fsm.on_person_frame(False)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

        # Re-confirmed presence within timeout -> GREETING
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.GREETING)
        self.assertIsNone(self.fsm.wake_pending_start_time)
        self.assertEqual(self.fsm.silence_count, 0)

    def test_partial_debouncing_interrupted_by_departure_resets_counter(self):
        self.fsm.wake_confirm_frames = 3
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.consecutive_wake_frames, 1)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)

        # Visitor leaves before debounce threshold
        self.fsm.on_person_frame(False)
        self.assertEqual(self.fsm.consecutive_wake_frames, 0)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)

        # Return requires 3 fresh frames
        self.fsm.on_person_frame(True)
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)
        self.fsm.on_person_frame(True)
        self.assertEqual(self.fsm.state, PortraitState.WAKE_PENDING)

    def test_speech_detection_resets_silence_counter(self):
        self.fsm.state = PortraitState.LISTENING
        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.silence_count, 1)
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)

        # Visitor speaks
        self.fsm.on_speech_detected()
        self.assertEqual(self.fsm.state, PortraitState.THINKING)
        self.assertEqual(self.fsm.silence_count, 0)

        # Conversation turn finishes back to LISTENING
        self.fsm.on_llm_response_ready()
        self.fsm.on_speaking_complete()
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)

        # Next silence starts at 1, not 2
        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.silence_count, 1)
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)

    def test_silence_in_non_listening_state_is_safely_ignored(self):
        for non_listening in (PortraitState.IDLE, PortraitState.WAKE_PENDING,
                              PortraitState.GREETING, PortraitState.THINKING,
                              PortraitState.SPEAKING, PortraitState.COOLDOWN):
            with self.subTest(state=non_listening):
                self.fsm.state = non_listening
                self.fsm.silence_count = 0
                self.fsm.on_speech_silence()
                self.assertEqual(self.fsm.state, non_listening)
                self.assertEqual(self.fsm.silence_count, 0)

    def test_configurable_max_consecutive_silence(self):
        self.fsm.max_consecutive_silence = 3
        self.fsm.state = PortraitState.LISTENING

        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)
        self.assertEqual(self.fsm.silence_count, 1)

        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.state, PortraitState.LISTENING)
        self.assertEqual(self.fsm.silence_count, 2)

        # 3rd silence reaches threshold -> enters COOLDOWN
        self.fsm.on_speech_silence()
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.assertTrue(self.fsm._cooldown_presence_latched)

    def test_turn_failure_recovery_via_cooldown_and_resume_on_speech(self):
        self.fsm.state = PortraitState.THINKING
        # Simulate failed turn handling (as performed by TalkingPortraitApp._turn_failed)
        self.fsm.start_cooldown()
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)
        self.assertTrue(self.fsm._cooldown_presence_latched)
        self.assertIsNotNone(self.fsm.cooldown_start_time)

        # Visitor asks a question again during COOLDOWN -> responsive recovery to THINKING
        self.fsm.on_speech_detected()
        self.assertEqual(self.fsm.state, PortraitState.THINKING)
        self.assertIsNone(self.fsm.cooldown_start_time)
        self.assertEqual(self.fsm.silence_count, 0)

    def test_turn_failure_with_visitor_departure_accelerates_return_to_idle(self):
        self.fsm.state = PortraitState.THINKING
        self.fsm.presence_loss_frames = 2
        self.fsm.presence_loss_cooldown_duration = 0.1
        self.fsm.cooldown_duration = 5.0

        # Turn fails and caller triggers cooldown
        self.fsm.start_cooldown()
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)

        # Visitor leaves during cooldown
        self.fsm.on_person_frame(False)
        self.assertFalse(self.fsm._cooldown_presence_latched)
        self.fsm.on_person_frame(False)
        self.assertTrue(self.fsm._presence_lost)

        # Accelerated cooldown elapses
        time.sleep(0.15)
        self.fsm.update(visual_ready=True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)

    def test_turn_failure_cooldown_respects_visual_readiness(self):
        self.fsm.state = PortraitState.THINKING
        self.fsm.cooldown_duration = 0.05
        self.fsm.start_cooldown()

        time.sleep(0.1)
        # Visual transition not ready yet -> stays COOLDOWN
        self.fsm.update(visual_ready=False)
        self.assertEqual(self.fsm.state, PortraitState.COOLDOWN)

        # Visual becomes ready -> transitions to IDLE
        self.fsm.update(visual_ready=True)
        self.assertEqual(self.fsm.state, PortraitState.IDLE)



if __name__ == "__main__":
    unittest.main()
