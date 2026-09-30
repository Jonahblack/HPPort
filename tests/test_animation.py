"""Unit tests for the upgraded animation engine (Visemes, Blinking, Saccades)."""

import time
import unittest
from unittest.mock import patch
from renderer.animation import BlinkController, SaccadeController, LipSyncEngine, VISEME_NAMES
from vision.mock import MockVision


class TestAnimationEngine(unittest.TestCase):

    def test_blink_controller_stages_and_progress(self):
        controller = BlinkController(min_interval_sec=0.01, max_interval_sec=0.02, blink_duration_ms=100)
        # Initially open
        self.assertEqual(controller.get_stage(), "open")
        self.assertEqual(controller.get_progress(), 0.0)

        # Trigger blink
        controller.is_blinking = True
        controller.blink_start_time = time.monotonic() - 0.02
        controller.update()
        self.assertIn(controller.get_stage(), ("open", "half"))

        # Middle of blink (50ms in) -> closed
        controller.blink_start_time = time.monotonic() - 0.05
        controller.update()
        self.assertEqual(controller.get_stage(), "closed")
        self.assertGreaterEqual(controller.get_progress(), 0.75)

    def test_saccade_controller_produces_bounded_jitter(self):
        saccade = SaccadeController(min_interval=0.01, max_interval=0.02, max_jitter_px=3.0)
        # Trigger saccade
        saccade.next_saccade_time = time.monotonic() - 1.0
        jx, jy = saccade.update()
        self.assertLessEqual(abs(jx), 4.0)
        self.assertLessEqual(abs(jy), 4.0)

    def test_lipsync_engine_viseme_mapping(self):
        engine = LipSyncEngine()
        # Test Preston Blair visemes
        self.assertEqual(engine.viseme_to_legacy_index("A"), 1)
        self.assertEqual(engine.viseme_to_legacy_index("X"), 1)
        self.assertEqual(engine.viseme_to_legacy_index("B"), 2)
        self.assertEqual(engine.viseme_to_legacy_index("C"), 3)
        self.assertEqual(engine.viseme_to_legacy_index("D"), 3)

        # Test crossfade alpha
        engine.set_active_viseme("B")
        time.sleep(0.04)
        self.assertGreaterEqual(engine.get_crossfade_alpha(), 0.8)

    def test_saccade_easing_is_independent_of_frame_rate(self):
        offsets = []
        for fps in (30, 60):
            with patch("renderer.animation.time.monotonic", return_value=0.0) as now:
                saccade = SaccadeController()
                saccade.target_offset_x = 2.0
                saccade.next_saccade_time = 10.0
                saccade.saccade_end_time = 10.0
                for frame in range(1, fps + 1):
                    now.return_value = frame / fps
                    saccade.update()
                offsets.append(saccade.current_offset_x)
        self.assertAlmostEqual(*offsets, places=6)

    def test_mock_gaze_moves_without_rendering_preview(self):
        with patch("vision.mock.time.monotonic", return_value=0.0) as now:
            vision = MockVision()
            vision.start()
            vision.trigger(10.0)
            initial = vision.get_visitor_gaze()
            now.return_value = 0.5
            self.assertNotEqual(initial, vision.get_visitor_gaze())
            vision.stop()

    def test_mock_vision_gaze_tracking(self):
        vision = MockVision()
        vision.start()
        # Without presence
        gaze = vision.get_visitor_gaze()
        self.assertEqual(gaze, (0.0, 0.0, 1.0))

        # With presence
        vision.trigger(duration_seconds=2.0)
        gaze = vision.get_visitor_gaze()
        self.assertIsInstance(gaze, tuple)
        self.assertEqual(len(gaze), 3)
        gx, gy, gdist = gaze
        self.assertGreaterEqual(gx, -1.0)
        self.assertLessEqual(gx, 1.0)
        self.assertGreater(gdist, 0.0)
        vision.stop()


if __name__ == "__main__":
    unittest.main()
