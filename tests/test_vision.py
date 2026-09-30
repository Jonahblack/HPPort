"""Unit tests for the Raspberry Pi vision driver fallback behavior."""

import time
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

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
        self.assertIs(frame, self.vision._build_standby_frame())

    def test_visitor_gaze_returns_valid_tuple(self):
        gaze = self.vision.get_visitor_gaze()
        self.assertIsInstance(gaze, tuple)
        self.assertEqual(len(gaze), 3)
        self.assertEqual(gaze, (0.0, 0.0, 1.0))

    def test_preview_cache_reuses_frame_without_modifying_capture(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.vision._latest_frame = frame
        self.vision._bounding_box = (40, 40, 80, 100)
        first = self.vision.get_latest_frame((200, 150))
        self.assertIsNotNone(first)
        self.assertEqual(first.get_size(), (200, 150))
        self.assertIs(first, self.vision.get_latest_frame((200, 150)))
        self.assertFalse(frame.any(), "Detection annotations must not alter captured pixels")
        self.vision._latest_frame = frame.copy()
        self.assertIsNot(first, self.vision.get_latest_frame((200, 150)))

    def test_preview_preserves_rgb_colors_and_invalidates_for_new_size(self):
        frame = np.full((120, 160, 3), (220, 60, 20), dtype=np.uint8)
        self.vision._latest_frame = frame
        first = self.vision.get_latest_frame()
        self.assertEqual(first.get_at((0, 0))[:3], (220, 60, 20))
        second = self.vision.get_latest_frame((80, 60))
        self.assertEqual(second.get_size(), (80, 60))
        self.assertEqual(second.get_at((0, 0))[:3], (220, 60, 20))
        self.assertIsNot(first, second)

    def test_camera_capture_honors_analysis_interval(self):
        now = [0.0]
        frames = [0]
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        source = {"type": "test"}

        def read(_source):
            frames[0] += 1
            if frames[0] >= 10:
                self.vision._running = False
            return frame

        def advance(_timeout):
            now[0] += 1 / 30

        self.vision.poll_interval = 0.1
        self.vision.target_fps = 30
        self.vision._stop_event = MagicMock()
        self.vision._stop_event.wait.side_effect = advance
        with patch("vision.hailo.time.monotonic", side_effect=lambda: now[0]), \
                patch.object(self.vision, "_open_camera_source", return_value=source), \
                patch.object(self.vision, "_read_camera_frame", side_effect=read), \
                patch.object(self.vision, "_analyze_frame", return_value=(False, 0.0, None)) as analyze, \
                patch.object(self.vision, "_close_camera_source") as close:
            self.vision._capture_loop()
        self.assertEqual(frames[0], 10)
        self.assertGreaterEqual(analyze.call_count, 3)
        self.assertLessEqual(analyze.call_count, 4)
        close.assert_called_once_with(source)

    def test_capture_error_releases_camera_and_reports_failure(self):
        source = {"type": "test"}
        with patch.object(self.vision, "_open_camera_source", return_value=source), \
                patch.object(self.vision, "_read_camera_frame", side_effect=RuntimeError("Disconnected")), \
                patch.object(self.vision, "_close_camera_source") as close:
            self.vision._capture_loop()
        close.assert_called_once_with(source)
        self.assertFalse(self.vision._running)
        self.assertIn("Disconnected", self.vision.get_status_info()["camera_error"])

    def test_picamera_startup_failure_closes_camera_for_backend_fallback(self):
        picamera_module = MagicMock()
        camera = picamera_module.Picamera2.return_value
        camera.configure.side_effect = RuntimeError("Unsupported format")
        with patch.dict(sys.modules, {"picamera2": picamera_module}):
            with self.assertRaisesRegex(RuntimeError, "Unsupported format"):
                self.vision._open_picamera2()
        camera.close.assert_called_once()
        self.assertEqual(camera.create_video_configuration.call_args.kwargs["main"]["format"], "BGR888")

    def test_downsampled_motion_reports_original_image_coordinates(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("OpenCV is required for motion detection")
        self.vision.analysis_width = 320
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertFalse(self.vision._analyze_frame(frame)[0])
        frame[80:240, 320:480] = 255
        detected, confidence, bbox = self.vision._analyze_frame(frame)
        self.assertTrue(detected)
        self.assertGreaterEqual(confidence, self.vision.confidence_threshold)
        self.assertEqual(self.vision._prev_gray.shape, (240, 320))
        x, y, width, height = bbox
        self.assertTrue(300 <= x <= 330)
        self.assertTrue(60 <= y <= 90)
        self.assertTrue(140 <= width <= 190)
        self.assertTrue(140 <= height <= 190)

    def test_diagnostics_distinguish_sdk_import_from_accelerated_inference(self):
        self.vision._hailo_initialized = True
        status = self.vision.get_status_info()
        self.assertEqual(status["detector"], "motion")
        self.assertFalse(status["hailo_inference_active"])


if __name__ == "__main__":
    unittest.main()
