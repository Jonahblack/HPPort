"""Asset validation, deterministic review publication, and failure preservation."""

import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

from renderer.asset_catalog import load_catalog
from tools.process_wilhelm_assets import process


class TestAssetCatalog(unittest.TestCase):
    def fixture(self, root):
        source = root / "originals"
        source.mkdir()
        video = source / "test.mp4"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 24, (64, 36))
        self.assertTrue(writer.isOpened())
        for value in range(8):
            writer.write(np.full((36, 64, 3), value * 20, dtype=np.uint8))
        writer.release()
        cv2.imwrite(str(source / "still.png"), np.zeros((36, 64, 3), dtype=np.uint8))
        catalog = {
            "version": "2.0", "source_dir": "originals", "target_assets_dir": "assets",
            "initial_scene": "reading", "scenes": {"reading": {"activity": "reading"}},
            "clips": [{"id": "action", "source_file": "test.mp4", "source_fps": 24,
                       "start_frame": 0, "end_frame": None, "entry_scene": "reading",
                       "exit_scene": "reading", "runtime_enabled": True,
                       "review_status": "candidate", "audio": "muted"}],
            "stills": [{"source_file": "still.png", "target_file": "still.png"}],
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(catalog), encoding="utf-8")
        return path, catalog

    def test_publication_is_versioned_and_unchanged_on_later_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, catalog = self.fixture(root)
            original_bytes = (root / "originals/test.mp4").read_bytes()
            report = process(manifest)
            pointer = root / "assets/scene_catalog.json"
            published = pointer.read_bytes()
            self.assertEqual(report["clips"][0]["fps"], 24)
            self.assertEqual(report["clips"][0]["end_frame"], 8)
            self.assertTrue((root / "assets/review" / report["revision"] / "action/last.png").is_file())
            self.assertEqual(process(manifest)["revision"], report["revision"])
            self.assertEqual((root / "originals/test.mp4").read_bytes(), original_bytes)
            catalog["clips"][0]["end_frame"] = 99
            manifest.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid source range"):
                process(manifest)
            self.assertEqual(pointer.read_bytes(), published)

    def test_source_traversal_and_unimplemented_checkpoints_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, catalog = self.fixture(Path(directory))
            catalog["clips"][0]["source_file"] = "../outside.mp4"
            manifest.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes"):
                load_catalog(manifest)
            catalog["clips"][0]["source_file"] = "test.mp4"
            catalog["clips"][0]["checkpoints"] = ["middle"]
            manifest.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_end checkpoints"):
                load_catalog(manifest)

    def test_check_only_does_not_publish_or_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, _ = self.fixture(root)
            process(manifest, check_only=True)
            self.assertFalse((root / "assets").exists())


if __name__ == "__main__":
    unittest.main()
