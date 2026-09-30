"""Regression tests for conversation ownership and failure recovery."""

import queue
import threading
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from config import DEFAULT_CONFIG
from main import TalkingPortraitApp, main
from speech_pipeline import SpeechPipelineError
from state_machine import PortraitState, PortraitStateMachine


class TestTalkingPortraitApp(unittest.TestCase):
    def setUp(self):
        self.app = TalkingPortraitApp.__new__(TalkingPortraitApp)
        app = self.app
        app.config = deepcopy(DEFAULT_CONFIG)
        app.demo_mode = False
        app.running = True
        app._stop = threading.Event()
        app._events = queue.SimpleQueue()
        app._turn_id = 1
        app.is_listening_active = False
        app._listen_thread = None
        app._warmup_thread = None
        app.current_audio_thread = None
        app.conversation_history = []
        app.renderer = Mock()
        app.stt = Mock()
        app.safeguard = Mock()
        app.safeguard.get_metrics.return_value = {"daily_used": 1000, "daily_limit": 1000, "status_text": "EXCEEDED"}
        app.live_client = Mock()
        app.live_client.is_available.return_value = (False, "quota exhausted")
        app.fsm = PortraitStateMachine(app.config, app._on_state_change)
        app._ensure_listener = Mock()
        app.listen_timeout_seconds = 4.0
        app.max_listen_duration_seconds = 10.0

    def run_worker(self):
        self.app.current_audio_thread.join(timeout=2)
        self.assertFalse(self.app.current_audio_thread.is_alive())
        self.app._drain_events()

    def test_listener_reopens_capture_after_first_silence(self):
        app = self.app
        app.fsm.state = PortraitState.LISTENING
        app.is_listening_active = True
        app.stt.listen_and_transcribe.return_value = None
        app._listen_worker(app._turn_id)
        # Workers cannot mutate the state machine before the display processes events.
        self.assertEqual(app.fsm.silence_count, 0)
        app._drain_events()
        self.assertEqual(app.fsm.silence_count, 1)
        self.assertFalse(app.is_listening_active)
        app._ensure_listener.assert_called_once()

    def test_stale_microphone_result_cannot_enter_a_new_listening_turn(self):
        app = self.app
        app.fsm.state = PortraitState.LISTENING
        app._generate_and_speak = Mock()
        app._on_listen_result(0, "Old microphone audio", 1.0, None)
        app._generate_and_speak.assert_not_called()
        app._ensure_listener.assert_called_once()

    def test_keyboard_turn_from_idle_or_cooldown_prevents_overlap(self):
        for state in (PortraitState.IDLE, PortraitState.COOLDOWN):
            with self.subTest(state=state):
                app = self.app
                app.fsm.state = state
                app._generate_and_speak = Mock()
                app._submit_text("Hello")
                app._submit_text("Second keypress")
                self.assertEqual(app.fsm.state, PortraitState.THINKING)
                app._generate_and_speak.assert_called_once_with("Hello", 0.0)

    def test_generate_and_speak_falls_back_to_local_when_quota_exhausted(self):
        app = self.app
        app._execute_local_pipelined_turn = Mock(return_value="Greetings!")
        app._execute_gemini_live_turn = Mock()
        app._submit_text("Hello")
        self.run_worker()
        app._execute_gemini_live_turn.assert_not_called()
        app._execute_local_pipelined_turn.assert_called_once()
        self.assertEqual(app.fsm.state, PortraitState.LISTENING)

    def test_cloud_and_local_share_the_piper_pipeline_by_default(self):
        app = self.app
        app.live_client.is_available.return_value = (True, "OK")
        app._execute_pipelined_turn = Mock(return_value="Onward!")
        app._execute_gemini_live_turn = Mock()
        app._submit_text("Hello")
        self.run_worker()
        self.assertIs(app._execute_pipelined_turn.call_args.args[0], app.live_client)
        app._execute_gemini_live_turn.assert_not_called()

    def test_cloud_stream_failure_before_audio_falls_back(self):
        app = self.app
        app.live_client.is_available.return_value = (True, "OK")
        app._execute_pipelined_turn = Mock(side_effect=SpeechPipelineError(RuntimeError("offline"), []))
        app._execute_local_pipelined_turn = Mock(return_value="Local reply.")
        app._submit_text("Hello")
        self.run_worker()
        app._execute_local_pipelined_turn.assert_called_once()

    def test_partial_cloud_reply_is_not_repeated_by_local_model(self):
        app = self.app
        app.live_client.is_available.return_value = (True, "OK")
        app._execute_pipelined_turn = Mock(side_effect=SpeechPipelineError(RuntimeError("offline"), ["Already spoken."]))
        app._execute_local_pipelined_turn = Mock()
        app._submit_text("Hello")
        self.run_worker()
        app._execute_local_pipelined_turn.assert_not_called()
        self.assertEqual(app.conversation_history[-1]["content"], "Already spoken.")

    def test_playback_error_does_not_restart_response_with_another_model(self):
        app = self.app
        app.live_client.is_available.return_value = (True, "OK")
        app._execute_pipelined_turn = Mock(side_effect=SpeechPipelineError(RuntimeError("speaker lost"), [], "playback"))
        app._execute_local_pipelined_turn = Mock()
        app._submit_text("Hello")
        self.run_worker()
        app._execute_local_pipelined_turn.assert_not_called()
        self.assertEqual(app.fsm.state, PortraitState.COOLDOWN)

    def test_failed_local_response_does_not_leave_portrait_thinking(self):
        app = self.app
        app._execute_local_pipelined_turn = Mock(side_effect=RuntimeError("server down"))
        app._submit_text("Hello")
        self.run_worker()
        self.assertEqual(app.fsm.state, PortraitState.COOLDOWN)

    def test_history_bounded_and_cleared_between_visitors(self):
        app = self.app
        for index in range(10):
            app.fsm.state = PortraitState.SPEAKING
            app._finish_turn(app._turn_id, str(index), f"Answer {index}")
        self.assertEqual(len(app.conversation_history), 4)
        app.fsm.start_cooldown()
        self.assertEqual(app.conversation_history, [])

    def test_fullscreen_cli_is_forwarded(self):
        with patch("main.parse_args", return_value=Mock(config="pi.json", demo=False, fullscreen=True)), patch("main.TalkingPortraitApp") as app:
            main()
        app.assert_called_once_with("pi.json", demo_mode=False, fullscreen=True)

    def test_cleanup_closes_drivers_even_when_worker_is_absent(self):
        app = self.app
        app.vision, app.llm, app.tts = Mock(), Mock(), Mock()
        with patch("main.pygame.mixer.get_init", return_value=None):
            app.cleanup()
        self.assertTrue(app._stop.is_set())
        self.assertFalse(app.running)
        app.vision.stop.assert_called_once()
        app.tts.close.assert_called_once()
        app.live_client.close.assert_called_once()
        app.renderer.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
