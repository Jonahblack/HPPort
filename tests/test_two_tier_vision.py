"""Unit tests for the Two-Tier Vision Perception and Wake Intent Pipeline."""

import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from config import DEFAULT_CONFIG
from vision.base import BaseVisionDetector
from vision.hailo import HailoVision
from vision.mock import MockVision
from vision.person_detector import (
    DetectionResult,
    HailoPersonDetectorBackend,
    OpenCVPersonDetectorBackend,
    MotionDetectorBackend,
    SmartPersonDetector,
)
from vision.wake_word import (
    WakeTriggerResult,
    KeywordFilterDetector,
    GazeDwellTrigger,
    TwoTierWakeController,
)


class TestDetectionResult(unittest.TestCase):

    def test_default_initialization(self):
        res = DetectionResult()
        self.assertFalse(res.detected)
        self.assertEqual(res.confidence, 0.0)
        self.assertIsNone(res.bbox)
        self.assertEqual(res.class_name, "none")
        self.assertEqual(res.distance, 1.0)
        self.assertEqual(res.gaze, (0.0, 0.0, 1.0))

    def test_to_dict_formatting(self):
        res = DetectionResult(
            detected=True,
            confidence=0.8765,
            bbox=(10, 20, 100, 200),
            class_name="person",
            backend="hailo",
            distance=1.234,
            facing_score=0.951,
            gaze=(0.123, -0.456, 1.234),
        )
        d = res.to_dict()
        self.assertTrue(d["detected"])
        self.assertEqual(d["confidence"], 0.876)
        self.assertEqual(d["bbox"], (10, 20, 100, 200))
        self.assertEqual(d["distance"], 1.234)
        self.assertEqual(d["facing_score"], 0.951)
        self.assertEqual(d["gaze"], (0.123, -0.456, 1.234))


class TestPersonDetectorBackends(unittest.TestCase):

    def test_hailo_backend_availability_check(self):
        backend = HailoPersonDetectorBackend(model_path="/nonexistent/model.hef")
        self.assertEqual(backend.name, "hailo")
        self.assertFalse(backend.is_available())
        diag = backend.get_diagnostics()
        self.assertFalse(diag["model_exists"])

    def test_opencv_backend_diagnostics(self):
        backend = OpenCVPersonDetectorBackend(confidence_threshold=0.6)
        self.assertEqual(backend.name, "opencv_dnn")
        self.assertTrue(backend.is_available())

    def test_motion_backend_detects_movement_between_frames(self):
        motion = MotionDetectorBackend(confidence_threshold=0.55, min_contour_area=500.0)
        self.assertEqual(motion.name, "motion")
        self.assertTrue(motion.is_available())

        frame1 = np.zeros((240, 320, 3), dtype=np.uint8)
        res1 = motion.detect(frame1)
        self.assertFalse(res1.detected)

        # Inject vertical motion silhouette (human aspect ratio)
        frame2 = frame1.copy()
        frame2[40:180, 120:180] = 255
        res2 = motion.detect(frame2)
        self.assertTrue(res2.detected)
        self.assertGreaterEqual(res2.confidence, 0.55)
        self.assertIsNotNone(res2.bbox)
        self.assertEqual(res2.class_name, "motion")
        self.assertGreater(res2.facing_score, 0.5)


class TestSmartPersonDetector(unittest.TestCase):

    def setUp(self):
        self.detector = SmartPersonDetector(DEFAULT_CONFIG)

    def test_initial_state(self):
        self.assertFalse(self.detector.is_person_present())
        self.assertFalse(self.detector.is_visitor_engaged())
        self.assertEqual(self.detector.get_dwell_seconds(), 0.0)
        self.assertEqual(self.detector.get_visitor_gaze(), (0.0, 0.0, 1.0))

    def test_dwell_accumulation_and_reset(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        # Prime background
        self.detector.analyze_frame(frame)

        # Inject centered vertical human contour in conversational zone
        frame_person = frame.copy()
        frame_person[30:190, 130:190] = 255
        res = self.detector.analyze_frame(frame_person)
        self.assertTrue(res.detected)
        self.assertTrue(self.detector.is_person_present())

        time.sleep(0.1)
        # Person micro-movement (breathing / slight sway)
        frame_person2 = frame.copy()
        frame_person2[33:193, 131:191] = 255
        res2 = self.detector.analyze_frame(frame_person2)
        self.assertTrue(res2.detected)
        dwell = self.detector.get_dwell_seconds()
        self.assertGreaterEqual(dwell, 0.08)

        # Move person out of frame -> dwell must reset to 0
        frame_empty = np.zeros((240, 320, 3), dtype=np.uint8)
        self.detector.analyze_frame(frame_empty)
        self.detector.analyze_frame(frame_empty)
        self.assertEqual(self.detector.get_dwell_seconds(), 0.0)

    def test_reset_clears_history(self):
        self.detector._smoothed_gaze_x = 0.5
        self.detector._smoothed_distance = 0.8
        self.detector.reset()
        self.assertEqual(self.detector._smoothed_gaze_x, 0.0)
        self.assertEqual(self.detector._smoothed_distance, 1.0)
        self.assertEqual(self.detector.get_dwell_seconds(), 0.0)


class TestWakeWordAndIntent(unittest.TestCase):

    def test_keyword_filter_matches_wilhelm(self):
        filter_det = KeywordFilterDetector(["wilhelm", "hey wilhelm"])
        self.assertIsNone(filter_det.check_text(""))
        self.assertIsNone(filter_det.check_text("Good morning good sir!"))

        match1 = filter_det.check_text("Hark, Wilhelm, can you hear me?")
        self.assertIsNotNone(match1)
        self.assertTrue(match1.triggered)
        self.assertEqual(match1.source, "wake_word")
        self.assertEqual(match1.keyword.lower(), "wilhelm")

        match2 = filter_det.check_text("hey wilhelm what time is it?")
        self.assertIsNotNone(match2)
        self.assertTrue(match2.triggered)
        self.assertEqual(match2.keyword.lower(), "hey wilhelm")

    def test_gaze_dwell_trigger(self):
        trigger = GazeDwellTrigger(dwell_threshold_seconds=0.3, max_distance=1.4, facing_tolerance=0.40)

        # 1. Not detected
        self.assertIsNone(trigger.evaluate(is_detected=False, dwell_seconds=0.5, gaze=(0.0, 0.0, 1.0)))

        # 2. Detected but looking far away
        self.assertIsNone(trigger.evaluate(is_detected=True, dwell_seconds=0.5, gaze=(0.8, 0.0, 1.0)))

        # 3. Detected and facing, but dwell < threshold
        self.assertIsNone(trigger.evaluate(is_detected=True, dwell_seconds=0.2, gaze=(0.1, 0.0, 1.0)))

        # 4. Dwell threshold satisfied -> Triggers wake
        res = trigger.evaluate(is_detected=True, dwell_seconds=0.35, gaze=(0.1, 0.0, 1.0))
        self.assertIsNotNone(res)
        self.assertTrue(res.triggered)
        self.assertEqual(res.source, "gaze_dwell")

        # 5. Subsequent evaluation in same session does not double-trigger
        self.assertIsNone(trigger.evaluate(is_detected=True, dwell_seconds=0.5, gaze=(0.1, 0.0, 1.0)))

        # 6. Looking away resets trigger
        trigger.evaluate(is_detected=True, dwell_seconds=0.5, gaze=(0.9, 0.0, 1.0))
        # Now facing again with threshold triggers anew
        res2 = trigger.evaluate(is_detected=True, dwell_seconds=0.35, gaze=(0.1, 0.0, 1.0))
        self.assertIsNotNone(res2)
        self.assertTrue(res2.triggered)

    def test_two_tier_wake_controller_modes(self):
        cfg = {"vision": {"two_tier": {"enabled": True, "tier2_wake_mode": "hybrid", "gaze_dwell_threshold_seconds": 0.2}}}
        controller = TwoTierWakeController(cfg)

        # A. Hybrid mode with keyword
        res_kw = controller.evaluate_wake_intent(
            person_detected=True,
            dwell_seconds=0.05,
            gaze=(0.0, 0.0, 1.0),
            transcript_text="Wilhelm, wake up!",
        )
        self.assertTrue(res_kw.triggered)
        self.assertEqual(res_kw.source, "wake_word")

        # B. Hybrid mode with dwell
        controller.reset()
        res_dwell = controller.evaluate_wake_intent(
            person_detected=True,
            dwell_seconds=0.25,
            gaze=(0.0, 0.0, 1.0),
        )
        self.assertTrue(res_dwell.triggered)
        self.assertEqual(res_dwell.source, "gaze_dwell")

        # C. Wake word only mode ignores dwell
        controller.wake_mode = "wake_word_only"
        controller.reset()
        res_ignored = controller.evaluate_wake_intent(
            person_detected=True,
            dwell_seconds=0.5,
            gaze=(0.0, 0.0, 1.0),
        )
        self.assertFalse(res_ignored.triggered)

        # D. Manual wake override
        man_res = controller.trigger_manual_wake(duration_seconds=0.2)
        self.assertTrue(man_res.triggered)
        self.assertEqual(man_res.source, "manual")


class TestHailoVisionTwoTierIntegration(unittest.TestCase):

    def setUp(self):
        self.vision = HailoVision(DEFAULT_CONFIG)
        self.vision._running = True

    def tearDown(self):
        self.vision._running = False

    def test_base_interface_compliance(self):
        self.assertIsInstance(self.vision, BaseVisionDetector)
        self.assertFalse(self.vision.is_person_present())
        self.assertFalse(self.vision.is_visitor_engaged())
        self.assertEqual(self.vision.get_visitor_proximity(), 1.0)
        self.assertEqual(self.vision.get_dwell_seconds(), 0.0)

    def test_presence_metrics_dictionary(self):
        metrics = self.vision.get_presence_metrics()
        self.assertIn("present", metrics)
        self.assertIn("engaged", metrics)
        self.assertIn("proximity", metrics)
        self.assertIn("dwell_seconds", metrics)
        self.assertIn("gaze", metrics)
        self.assertIn("wake_triggered", metrics)

    def test_manual_override_activates_two_tier(self):
        self.vision.simulate_detection(True, duration_seconds=0.2)
        self.assertTrue(self.vision.is_person_present())
        self.assertTrue(self.vision.is_visitor_engaged())
        self.assertTrue(self.vision.is_wake_triggered())


class TestMockVisionTwoTierIntegration(unittest.TestCase):

    def setUp(self):
        self.vision = MockVision()
        self.vision.start()

    def tearDown(self):
        self.vision.stop()

    def test_simulate_presence_sets_distance_and_dwell(self):
        self.vision.simulate_presence(True, distance=0.8, duration_seconds=0.3)
        self.assertTrue(self.vision.is_person_present())
        self.assertEqual(self.vision.get_visitor_proximity(), 0.8)

        time.sleep(0.25)
        self.assertTrue(self.vision.is_visitor_engaged())

    def test_simulate_wake_word_triggers_wake(self):
        self.vision.simulate_wake_word("Wilhelm", duration_seconds=0.2)
        self.assertTrue(self.vision.is_wake_triggered())
        res = self.vision.evaluate_wake_intent()
        self.assertTrue(res.triggered)
        self.assertEqual(res.source, "wake_word")
        self.assertEqual(res.keyword, "Wilhelm")


if __name__ == "__main__":
    unittest.main()
