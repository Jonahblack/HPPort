import json
import os
import tempfile
import unittest
from copy import deepcopy

from config import DEFAULT_CONFIG, load_config


class TestConfig(unittest.TestCase):
    def test_nested_overrides_and_demo_do_not_mutate_defaults(self):
        original = deepcopy(DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "portrait.json")
            with open(path, "w") as stream:
                json.dump({"renderer": {"sprite_files": {"base": "custom.png"}}}, stream)
            demo = load_config(path, demo_mode=True)
            normal = load_config(path)
        self.assertEqual(DEFAULT_CONFIG, original)
        self.assertEqual(normal["vision"]["driver"], "hailo")
        self.assertEqual(demo["renderer"]["sprite_files"]["base"], "custom.png")
        self.assertIn("eyes_closed", demo["renderer"]["sprite_files"])
        self.assertFalse(demo["gemini_live"]["enabled"])
        self.assertIsNone(demo["hardware"]["audio_dir"])

    def test_invalid_section_does_not_silently_use_wrong_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "portrait.json")
            with open(path, "w") as stream:
                json.dump({"renderer": None}, stream)
            with self.assertRaisesRegex(ValueError, "renderer must be an object"):
                load_config(path)

    def test_zero_fps_rejected_before_audio_division(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "portrait.json")
            with open(path, "w") as stream:
                json.dump({"renderer": {"fps": 0}}, stream)
            with self.assertRaisesRegex(ValueError, "renderer.fps"):
                load_config(path)
