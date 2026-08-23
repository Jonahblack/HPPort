"""Unit tests for STT and TTS drivers."""

import os
import unittest
from stt.keyboard_stt import KeyboardSTT
from tts.mock_tts import MockTTS


class TestSTTTTS(unittest.TestCase):

    def test_keyboard_stt(self):
        stt = KeyboardSTT()
        stt.inject_text("Halt and state your business!")
        transcribed = stt.listen_and_transcribe(timeout_seconds=0.5)
        self.assertEqual(transcribed, "Halt and state your business!")

    def test_mock_tts_synthesis(self):
        tts = MockTTS()
        out_path = "/tmp/test_speech.wav"
        path, duration = tts.synthesize_to_file("A true knight never backs down!", out_path)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(duration, 0.5)

        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
