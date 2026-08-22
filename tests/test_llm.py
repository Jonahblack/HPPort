"""
Unit tests for LLM client implementations.
"""

import unittest
from llm.llama_client import LlamaClient
from llm.mock_client import MockLLMClient


class TestLLM(unittest.TestCase):
    def test_mock_llm_generation(self):
        client = MockLLMClient(system_prompt="Test Prompt", artificial_delay_seconds=0.01)
        resp = client.generate("Hello!")
        self.assertTrue(len(resp.text) > 0)
        self.assertTrue(resp.metrics.tokens_generated > 0)

    def test_mock_llm_streaming(self):
        client = MockLLMClient(artificial_delay_seconds=0.01)
        chunks = list(client.generate_stream("Hello"))
        self.assertTrue(len(chunks) > 0)
        full_text = "".join(chunks)
        self.assertTrue(len(full_text) > 0)

    def test_llama_payload_structure(self):
        client = LlamaClient(
            endpoint_url="http://127.0.0.1:8080/v1/chat/completions",
            model_name="gemma-4-e2b-instruct",
            system_prompt="Knight persona",
        )
        payload = client._build_payload("What is your sword named?", conversation_history=[{"role": "user", "content": "Hi"}])
        self.assertEqual(payload["model"], "gemma-4-e2b-instruct")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][0]["content"], "Knight persona")
        self.assertEqual(payload["messages"][-1]["content"], "What is your sword named?")


if __name__ == "__main__":
    unittest.main()
