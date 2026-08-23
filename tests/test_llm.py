"""Unit tests for LLM drivers."""

import unittest
from llm.mock_client import MockLLMClient


class TestLLM(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MockLLMClient()

    def test_mock_llm_response(self):
        response = self.mock_llm.generate_response("Hello, what is your name?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 10)
        self.assertIn("Cadogan", response)

    def test_mock_llm_password(self):
        response = self.mock_llm.generate_response("What is the password to the common room?")
        self.assertTrue("Caput Draconis" in response or "password" in response.lower())


if __name__ == "__main__":
    unittest.main()
