"""Native audio ordering and shutdown without sound hardware or cloud requests."""

import threading
import time
import unittest
import wave
from unittest.mock import Mock, patch

from main import TalkingPortraitApp


class FakeChannel:
    """A one-sound queue that advances as a real mixer channel would."""

    def __init__(self):
        self.current = self.queued = None
        self.deadline = 0.0
        self.played = []
        self.stopped = False

    def play(self, sound):
        self.current = sound
        self.played.append(sound)
        self.deadline = time.monotonic() + 0.02

    def queue(self, sound):
        if self.queued is not None:
            raise AssertionError("Replacing queued PCM loses audio")
        self.queued = sound

    def advance(self):
        if self.current is not None and time.monotonic() >= self.deadline:
            self.current = None
            if self.queued is not None:
                sound, self.queued = self.queued, None
                self.play(sound)

    def get_busy(self):
        self.advance()
        return self.current is not None

    def get_queue(self):
        self.advance()
        return self.queued

    def stop(self):
        self.stopped = True
        self.current = self.queued = None


class TestNativePlayback(unittest.TestCase):
    def setUp(self):
        self.app = TalkingPortraitApp.__new__(TalkingPortraitApp)
        self.app._stop = threading.Event()
        self.app._turn_id = 1
        self.app.conversation_history = []
        self.app.renderer = Mock()
        self.app.live_client = Mock()
        self.app._post = Mock()

    @staticmethod
    def sound_from_wav(*, file):
        with wave.open(file, "rb") as wav:
            assert wav.getframerate() == 24000
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            return wav.readframes(wav.getnframes())

    def call_bounded(self):
        finished = threading.Event()
        result, errors = [], []

        def call():
            try:
                result.append(self.app._execute_gemini_live_turn("Hello", 0, time.perf_counter()))
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        ended = finished.wait(2)
        self.app._stop.set()
        worker.join(1)
        self.assertTrue(ended, "Native playback did not drain/terminate")
        if errors:
            raise errors[0]
        return result[0]

    def test_all_pcm_chunks_play_in_order_on_one_channel_before_return(self):
        pcm = [bytes([index, 0]) * 20 for index in (1, 2, 3, 4)]
        channel = FakeChannel()

        def execute(text, audio, transcript, **kwargs):
            transcript("assistant", "Onward")
            for chunk in pcm:
                audio(chunk)
            transcript("assistant", ", brave traveler!")
            return True

        self.app.live_client.execute_turn.side_effect = execute
        with patch("main.pygame.mixer.Channel", return_value=channel) as make_channel, \
                patch("main.pygame.mixer.Sound", side_effect=self.sound_from_wav):
            reply = self.call_bounded()
        self.assertEqual(reply, "Onward, brave traveler!")
        self.assertEqual(channel.played, pcm)
        self.assertFalse(channel.get_busy())
        self.assertIsNone(channel.get_queue())
        make_channel.assert_called_once_with(0)
        self.app._post.assert_called_once_with(self.app._begin_speaking, 1)

    def test_partial_cloud_failure_keeps_already_audible_reply(self):
        def execute(text, audio, transcript, **kwargs):
            audio(b"\x01\x00" * 20)
            transcript("assistant", "Onward!")
            return False

        self.app.live_client.execute_turn.side_effect = execute
        with patch("main.pygame.mixer.Channel", return_value=FakeChannel()), \
                patch("main.pygame.mixer.Sound", side_effect=self.sound_from_wav):
            self.assertEqual(self.call_bounded(), "Onward!")

    def test_empty_cloud_response_returns_none_for_local_fallback(self):
        self.app.live_client.execute_turn.return_value = False
        with patch("main.pygame.mixer.Channel", return_value=FakeChannel()):
            self.assertIsNone(self.call_bounded())

    def test_missing_audio_device_does_not_deadlock_a_full_receive_queue(self):
        def execute(text, audio, transcript, **kwargs):
            try:
                for _ in range(40):
                    audio(b"\x01\x00" * 20)
            except RuntimeError:
                return False
            return True

        self.app.live_client.execute_turn.side_effect = execute
        with patch("main.pygame.mixer.Channel", side_effect=RuntimeError("speaker unavailable")):
            with self.assertRaisesRegex(RuntimeError, "speaker unavailable"):
                self.call_bounded()
