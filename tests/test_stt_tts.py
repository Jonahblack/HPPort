"""
Unit tests for STT, TTS, Animation, and Vision simulators.
"""

import time
import unittest
from renderer.animation import AnimationController, MouthFrame
from stt.keyboard_stt import KeyboardSTT
from tts.mock_tts import MockTTS
from vision.mock import MockVision


class TestAudioAndVision(unittest.TestCase):
    def test_mock_tts_amplitude_generation(self):
        tts = MockTTS()
        res = tts.synthesize("A grand spell echoes in the corridor!")
        self.assertIsNotNone(res.amplitudes)
        self.assertTrue(len(res.amplitudes) > 0)
        # All amplitudes should be within 0.0 to 1.0 range
        for amp in res.amplitudes:
            self.assertTrue(0.0 <= amp <= 1.0)

    def test_animation_mouth_mapping(self):
        anim = AnimationController()
        anim.set_audio_amplitude(0.02)
        self.assertEqual(anim.mouth_frame, MouthFrame.CLOSED)

        anim.set_audio_amplitude(0.25)
        self.assertEqual(anim.mouth_frame, MouthFrame.PARTIAL)

        anim.set_audio_amplitude(0.75)
        self.assertEqual(anim.mouth_frame, MouthFrame.OPEN)

    def test_keyboard_stt_injection(self):
        stt = KeyboardSTT()
        captured = []
        stt.start_listening(callback=lambda res: captured.append(res.text))
        stt.inject_text("Lumos!")
        self.assertEqual(captured, ["Lumos!"])
        stt.stop_listening()

    def test_mock_vision_trigger(self):
        vision = MockVision(poll_interval_seconds=0.01)
        frames = []
        vision.start(callback=lambda f: frames.append(f.person_detected))
        vision.trigger_visitor(duration_frames=2)
        time.sleep(0.05)
        vision.stop()
        self.assertTrue(any(frames))


if __name__ == "__main__":
    unittest.main()
