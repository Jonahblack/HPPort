"""Unit tests for TokenSafeguard budget manager."""

import os
import shutil
import tempfile
import unittest

from live.safeguard import TokenSafeguard


class TestTokenSafeguard(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config = {
            "gemini_live": {
                "enabled": True,
                "max_daily_tokens": 1000,
                "max_session_tokens": 300,
                "storage_file": "test_tokens.json",
            },
            "hardware": {
                "cache_dir": self.test_dir,
            },
        }
        self.guard = TokenSafeguard(self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_initial_state_can_use_api(self):
        can_use, reason = self.guard.can_use_live_api()
        self.assertTrue(can_use)
        self.assertEqual(reason, "OK")

    def test_record_usage_increments_and_persists(self):
        self.guard.record_usage(total_tokens=250)
        self.assertEqual(self.guard.daily_tokens, 250)
        self.assertEqual(self.guard.session_tokens, 250)

        # Reload from disk
        new_guard = TokenSafeguard(self.config)
        self.assertEqual(new_guard.daily_tokens, 250)

    def test_session_limit_blocks_api(self):
        self.guard.record_usage(total_tokens=350)
        can_use, reason = self.guard.can_use_live_api()
        self.assertFalse(can_use)
        self.assertIn("Visitor session ceiling reached", reason)

        # Resetting session restores access
        self.guard.reset_session()
        can_use, reason = self.guard.can_use_live_api()
        self.assertTrue(can_use)

    def test_daily_limit_blocks_api_even_after_session_reset(self):
        self.guard.record_usage(total_tokens=1200)
        can_use, reason = self.guard.can_use_live_api()
        self.assertFalse(can_use)
        self.assertIn("Daily token ceiling reached", reason)

        self.guard.reset_session()
        can_use, reason = self.guard.can_use_live_api()
        self.assertFalse(can_use)

    def test_metrics_reporting(self):
        self.guard.record_usage(total_tokens=150)
        metrics = self.guard.get_metrics()
        self.assertEqual(metrics["daily_used"], 150)
        self.assertEqual(metrics["daily_limit"], 1000)
        self.assertEqual(metrics["daily_percent"], 15.0)
        self.assertEqual(metrics["status_text"], "SAFE")
        self.assertFalse(metrics["is_locked"])


if __name__ == "__main__":
    unittest.main()
