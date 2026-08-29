"""Unit tests for LLM drivers."""

import unittest
from unittest.mock import Mock, patch

from llm.llama_client import LlamaClient
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

    def test_llama_endpoint_is_normalized(self):
        config = {"llm": {"endpoint_url": "http://127.0.0.1:8080"}}
        client = LlamaClient(config)
        self.assertEqual(client.endpoint_url, "http://127.0.0.1:8080/v1/chat/completions")

    @patch("llm.llama_client.requests.post")
    def test_llama_client_uses_configured_timeout_tuple(self, mock_post):
        from requests.exceptions import RequestException

        mock_post.side_effect = RequestException("stop after assert")
        config = {"llm": {"endpoint_url": "http://127.0.0.1:8080", "timeout_seconds": 42.0, "connect_timeout_seconds": 3.0}}
        client = LlamaClient(config)
        client.generate_response("Hello there")
        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], (3.0, 42.0))

    @patch("llm.llama_client.requests.get")
    def test_llama_model_resolution_uses_sole_available_model(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "/mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf"}
            ]
        }
        mock_get.return_value = mock_response

        config = {"llm": {"endpoint_url": "http://127.0.0.1:8080", "model_name": "gemma-4-e2b-instruction"}}
        client = LlamaClient(config)
        resolved = client._resolve_model_name()
        self.assertEqual(resolved, "/mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf")

    @patch("llm.llama_client.requests.post")
    def test_llama_empty_content_uses_spoken_recovery(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": "", "reasoning_content": "hidden work"},
                }
            ],
            "usage": {"prompt_tokens": 30, "completion_tokens": 24},
        }
        mock_post.return_value = mock_response

        config = {"llm": {"empty_response_text": "Please ask again."}}
        client = LlamaClient(config)
        client._resolved_model_name = "test-model"

        self.assertEqual(client.generate_response("Hello"), "Please ask again.")

    @patch("llm.llama_client.requests.post")
    def test_llama_request_disables_thinking_and_limits_output(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": "Onward!"}}]
        }
        mock_post.return_value = mock_response

        client = LlamaClient({"llm": {"max_tokens": 24, "disable_reasoning": True}})
        client._resolved_model_name = "test-model"
        client.generate_response("Hello")

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["max_tokens"], 24)
        self.assertEqual(payload["n_predict"], 24)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})


if __name__ == "__main__":
    unittest.main()
