"""Unit tests for the Raspberry Pi vision driver fallback behavior."""

import time
import unittest

from config import DEFAULT_CONFIG
from vision.hailo import HailoVision


class TestHailoVision(unittest.TestCase):

    def setUp(self):
        self.config = dict(DEFAULT_CONFIG)
        self.config["vision"] = dict(DEFAULT_CONFIG["vision"])
        self.vision = HailoVision(self.config)
        self.vision._running = True

    def tearDown(self):
        self.vision._running = False

    def test_manual_detection_override_is_immediate(self):
        self.vision.simulate_detection(True, duration_seconds=0.2)
        self.assertTrue(self.vision.is_person_detected())
        self.assertGreaterEqual(self.vision.get_confidence(), 0.94)

        time.sleep(0.25)
        self.assertFalse(self.vision.is_person_detected())

    def test_standby_frame_matches_requested_dimensions(self):
        frame = self.vision._build_standby_frame()
        self.assertEqual(frame.shape, (self.vision.cam_height, self.vision.cam_width, 3))

    def test_visitor_gaze_returns_valid_tuple(self):
        gaze = self.vision.get_visitor_gaze()
        self.assertIsInstance(gaze, tuple)
        self.assertEqual(len(gaze), 3)
        self.assertEqual(gaze, (0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
