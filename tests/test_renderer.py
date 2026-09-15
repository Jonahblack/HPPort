"""Unit tests for PortraitRenderer logic, viseme mapping, and gaze tracking."""

import unittest
from unittest.mock import MagicMock, patch
import sys


class TestPortraitRenderer(unittest.TestCase):

    def setUp(self):
        # Provide a mock pygame if pygame is not installed in the current environment
        self.mock_pygame = MagicMock()
        self.mock_pygame.font = MagicMock()
        self.mock_pygame.mixer = MagicMock()
        self.mock_pygame.display = MagicMock()
        self.mock_pygame.image = MagicMock()
        self.mock_pygame.transform = MagicMock()
        self.mock_pygame.time = MagicMock()
        self.mock_pygame.Rect = MagicMock(side_effect=lambda x, y, w, h: MagicMock(
            topleft=(x, y), centerx=x + w//2, centery=y + h//2, width=w, height=h,
            inflate=lambda dx, dy: MagicMock(
                topleft=(x - dx//2, y - dy//2),
                centerx=x + w//2,
                centery=y + h//2,
                width=w + dx,
                height=h + dy,
                size=(w + dx, h + dy),
            ),
            size=(w, h),
        ))

    def test_gaze_target_clamping_and_updating(self):
        with patch.dict(sys.modules, {"pygame": self.mock_pygame}):
            from renderer.renderer import PortraitRenderer

            config = {
                "renderer": {
                    "width": 800,
                    "height": 600,
                    "gaze_tracking_enabled": True,
                    "gaze_sensitivity_x": 1.0,
                    "gaze_sensitivity_y": 0.8,
                }
            }
            renderer = PortraitRenderer(config)
            self.assertEqual(renderer.target_gaze_x, 0.0)
            self.assertEqual(renderer.target_gaze_y, 0.0)

            # Test updating gaze target
            renderer.set_gaze_target(0.75, -0.5, distance=1.4)
            self.assertEqual(renderer.target_gaze_x, 0.75)
            self.assertEqual(renderer.target_gaze_y, -0.5)
            self.assertEqual(renderer.target_distance, 1.4)

            # Test clamping beyond [-1.0, 1.0]
            renderer.set_gaze_target(2.5, -3.0)
            self.assertEqual(renderer.target_gaze_x, 1.0)
            self.assertEqual(renderer.target_gaze_y, -1.0)

    def test_viseme_updating_and_legacy_fallback(self):
        with patch.dict(sys.modules, {"pygame": self.mock_pygame}):
            from renderer.renderer import PortraitRenderer

            config = {"renderer": {"width": 800, "height": 600}}
            renderer = PortraitRenderer(config)

            # Test viseme 'D' (wide open)
            renderer.set_viseme("D", amplitude=0.85)
            self.assertEqual(renderer.current_viseme, "D")
            self.assertEqual(renderer.current_mouth_index, 3)
            self.assertEqual(renderer.audio_amplitude, 0.85)

            # Test viseme 'B' (consonants)
            renderer.set_viseme("B", amplitude=0.25)
            self.assertEqual(renderer.current_viseme, "B")
            self.assertEqual(renderer.current_mouth_index, 2)

            # Test viseme 'X' (rest)
            renderer.set_viseme("X", amplitude=0.0)
            self.assertEqual(renderer.current_viseme, "X")
            self.assertEqual(renderer.current_mouth_index, 1)

            # Test invalid viseme defaults to 'X'
            renderer.set_viseme("INVALID")
            self.assertEqual(renderer.current_viseme, "X")


if __name__ == "__main__":
    unittest.main()
