"""Tests for application orchestration behavior."""

import unittest
from unittest.mock import Mock

from main import TalkingPortraitApp
from state_machine import PortraitState, PortraitStateMachine


class TestTalkingPortraitApp(unittest.TestCase):
    def test_listener_reopens_capture_after_first_silence(self):
        app = TalkingPortraitApp.__new__(TalkingPortraitApp)
        app.running = True
        app.fsm = PortraitStateMachine({"state_machine": {"max_consecutive_silence": 2}})
        app.fsm.state = PortraitState.LISTENING
        app.stt = Mock()
        app.stt.listen_and_transcribe.side_effect = [None, "A quest awaits"]
        app.renderer = Mock()
        app.is_listening_active = False
        app.listen_timeout_seconds = 4.0
        app.max_listen_duration_seconds = 10.0
        app._generate_and_speak = Mock()

        app._listen_worker()

        self.assertEqual(app.stt.listen_and_transcribe.call_count, 2)
        app._generate_and_speak.assert_called_once_with(
            "A quest awaits",
            stt_duration=unittest.mock.ANY,
        )
        self.assertFalse(app.is_listening_active)


if __name__ == "__main__":
    unittest.main()
