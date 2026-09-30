"""Unit tests for LLM drivers."""

import unittest
from unittest.mock import Mock, patch

import requests

from llm.llama_client import LlamaClient
from llm.mock_client import MockLLMClient
from llm.streaming import speech_clauses


class TestLLM(unittest.TestCase):

    def setUp(self):
        self.mock_llm = MockLLMClient()

    def test_mock_llm_response(self):
        response = self.mock_llm.generate_response("Hello, what is your name?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 10)
        self.assertIn("Wilhelm", response)

    def test_mock_llm_password(self):
        response = self.mock_llm.generate_response("What is the password to the common room?")
        self.assertTrue("Caput Draconis" in response or "password" in response.lower())

    def test_llama_endpoint_is_normalized(self):
        config = {"llm": {"endpoint_url": "http://127.0.0.1:8080"}}
        client = LlamaClient(config)
        self.assertEqual(client.endpoint_url, "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(client._normalize_endpoint_url("http://127.0.0.1:8080/v1/"),
                         "http://127.0.0.1:8080/v1/chat/completions")

    @patch("llm.llama_client.requests.Session.post")
    def test_llama_client_uses_configured_timeout_tuple(self, mock_post):
        from requests.exceptions import RequestException

        mock_post.side_effect = RequestException("stop after assert")
        config = {"llm": {"endpoint_url": "http://127.0.0.1:8080", "timeout_seconds": 42.0, "connect_timeout_seconds": 3.0}}
        client = LlamaClient(config)
        client._resolved_model_name = "test-model"
        client.generate_response("Hello there")
        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], (3.0, 42.0))

    @patch("llm.llama_client.requests.Session.get")
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

    @patch("llm.llama_client.requests.Session.post")
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

    @patch("llm.llama_client.requests.Session.post")
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

    def test_generate_clauses_splits_on_boundaries(self):
        client = MockLLMClient()
        # Mock generate_response_stream to yield individual tokens
        tokens = ["Hark, ", "noble ", "traveler! ", "A ", "grand ", "quest ", "awaits ", "thee."]
        client.generate_response_stream = Mock(return_value=iter(tokens))

        clauses = list(client.generate_clauses("Hello"))
        self.assertGreaterEqual(len(clauses), 2)
        self.assertIn("Hark, noble traveler!", clauses[0])

    def test_zero_history_limit_excludes_all_old_messages(self):
        client = LlamaClient({"llm": {"history_turn_limit": 0}})
        messages = client._messages("Now", [{"role": "user", "content": "Old"}], None)
        self.assertEqual([item["content"] for item in messages[1:]], ["Now"])
        client.close()

    def test_stream_delivers_small_sse_events_and_closes_response(self):
        client = LlamaClient({})
        client._resolved_model_name = "test-model"
        response = Mock(status_code=200)
        response.iter_lines.return_value = [
            b": keepalive", b"data: broken json", b'data:{"choices":[{"delta":{"content":"Hark! "}}]}',
            b'data: {"choices":[{"delta":{"content":"Welcome."}}]}', b"data: [DONE]",
        ]
        with patch.object(client._session, "post", return_value=response):
            self.assertEqual(list(client.generate_response_stream("Hello")), ["Hark! ", "Welcome."])
        response.iter_lines.assert_called_once_with(chunk_size=1)
        response.close.assert_called_once()
        client.close()

    def test_cancelled_stream_closes_http_response(self):
        client = LlamaClient({})
        client._resolved_model_name = "test-model"
        response = Mock(status_code=200)
        response.iter_lines.return_value = iter([b'data: {"choices":[{"delta":{"content":"Hark!"}}]}'])
        with patch.object(client._session, "post", return_value=response):
            stream = client.generate_response_stream("Hello")
            self.assertEqual(next(stream), "Hark!")
            stream.close()
        response.close.assert_called_once()
        client.close()

    def test_partial_stream_failure_propagates_without_spoken_error(self):
        client = LlamaClient({})
        client._resolved_model_name = "test-model"
        response = Mock(status_code=200)

        def lines():
            yield b'data: {"choices":[{"delta":{"content":"Hark!"}}]}'
            raise requests.exceptions.ConnectionError("network lost")

        response.iter_lines.return_value = lines()
        with patch.object(client._session, "post", return_value=response):
            stream = client.generate_response_stream("Hello")
            self.assertEqual(next(stream), "Hark!")
            with self.assertRaises(requests.exceptions.ConnectionError):
                next(stream)
        response.close.assert_called_once()
        client.close()

    def test_sentence_boundaries_are_emitted_in_text_order(self):
        self.assertEqual(list(speech_clauses(["Hark! Come closer. Who are you? Welcome! "])),
                         ["Hark!", "Come closer.", "Who are you?", "Welcome!"])

    def test_phrase_boundary_across_tokens_keeps_word_and_punctuation(self):
        self.assertEqual(list(speech_clauses(["Hark, tra", "veler", "!", " Welcome."])),
                         ["Hark, traveler!", "Welcome."])

    def test_unpunctuated_speech_has_bounded_complete_words(self):
        result = list(speech_clauses(["one two three four five six seven eight nine ten eleven twelve thir", "teen"], max_words=7))
        self.assertEqual(result, ["one two three four five six seven", "eight nine ten eleven twelve thirteen"])

    def test_first_phrase_is_ready_before_more_tokens_are_requested(self):
        requested = []

        def source():
            yield "one two three four five six seven "
            requested.append(True)
            yield "and more words"

        clauses = speech_clauses(source())
        self.assertEqual(next(clauses), "one two three four five six seven")
        self.assertEqual(requested, [])
        clauses.close()

    def test_cancelling_clauses_closes_upstream_stream(self):
        closed = []

        def source():
            try:
                yield "Hark! A quest awaits. "
                yield "Onward."
            finally:
                closed.append(True)

        clauses = speech_clauses(source())
        self.assertEqual(next(clauses), "Hark!")
        clauses.close()
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
