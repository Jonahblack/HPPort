"""Unit tests for GeminiLiveClient and safeguard integration."""

import unittest
from unittest.mock import Mock, patch

from live.gemini_live import GeminiLiveClient
from live.safeguard import TokenSafeguard


class TestGeminiLiveClient(unittest.TestCase):
    def setUp(self):
        self.config = {
            "gemini_live": {
                "enabled": True,
                "model": "gemini-3.1-flash-live-preview",
                "voice_name": "Puck",
                "api_key_env": "TEST_GEMINI_KEY",
                "max_daily_tokens": 1000,
                "max_session_tokens": 500,
            },
            "hardware": {"cache_dir": "/tmp/test_cache"},
            "llm": {"system_prompt": "You are Lord Cadogan."},
        }

    def test_unavailable_when_key_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            client = GeminiLiveClient(self.config)
            available, reason = client.is_available()
            self.assertFalse(available)
            self.assertIn("API key not set", reason)

    def test_unavailable_when_quota_exceeded(self):
        safeguard = Mock(spec=TokenSafeguard)
        safeguard.can_use_live_api.return_value = (False, "Daily token ceiling reached")

        with patch.dict("os.environ", {"TEST_GEMINI_KEY": "dummy_key"}):
            client = GeminiLiveClient(self.config, safeguard=safeguard)
            client._genai_client = Mock()  # Mock SDK
            available, reason = client.is_available()
            self.assertFalse(available)
            self.assertIn("Daily token ceiling reached", reason)

    def test_available_when_key_and_quota_valid(self):
        safeguard = Mock(spec=TokenSafeguard)
        safeguard.can_use_live_api.return_value = (True, "OK")

        with patch.dict("os.environ", {"TEST_GEMINI_KEY": "dummy_key"}):
            client = GeminiLiveClient(self.config, safeguard=safeguard)
            client._genai_client = Mock()
            available, reason = client.is_available()
            self.assertTrue(available)
            self.assertEqual(reason, "OK")


if __name__ == "__main__":
    unittest.main()
