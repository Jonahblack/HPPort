"""Gemini transport tests; never contact Google or consume a paid quota."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from live.gemini_live import GeminiLiveClient
from live.safeguard import TokenSafeguard


class TestGeminiLiveClient(unittest.TestCase):
    def setUp(self):
        self.config = {
            "gemini_live": {"enabled": True, "api_key_env": "TEST_GEMINI_KEY"},
            "llm": {"system_prompt": "You are Lord Cadogan.", "history_turn_limit": 1},
        }
        self.safeguard = Mock(spec=TokenSafeguard)
        self.safeguard.can_use_live_api.return_value = (True, "OK")
        with patch.dict("os.environ", {"TEST_GEMINI_KEY": "test-key"}), patch.object(GeminiLiveClient, "_init_sdk"):
            self.client = GeminiLiveClient(self.config, self.safeguard)
        self.sdk = MagicMock()
        self.client._genai_client = self.sdk

    @staticmethod
    def chunk(text, total=0, prompt=0, output=0):
        return SimpleNamespace(text=text, usage_metadata=SimpleNamespace(
            total_token_count=total, prompt_token_count=prompt, candidates_token_count=output
        ))

    def test_unavailable_when_key_missing(self):
        self.client.api_key = ""
        available, reason = self.client.is_available()
        self.assertFalse(available)
        self.assertIn("API key not set", reason)

    def test_unavailable_when_quota_exceeded(self):
        self.safeguard.can_use_live_api.return_value = (False, "Daily token ceiling reached")
        with self.assertRaisesRegex(RuntimeError, "Daily token ceiling"):
            list(self.client.generate_response_stream("Hello"))
        self.sdk.models.generate_content_stream.assert_not_called()

    def test_available_when_key_and_quota_valid(self):
        self.assertEqual(self.client.is_available(), (True, "OK"))

    def test_stream_reuses_client_and_counts_cumulative_usage_once(self):
        self.sdk.models.generate_content_stream.return_value = iter([
            self.chunk("Hark! ", 10, 8, 2), self.chunk("Onward.", 15, 8, 7), self.chunk(None, 15, 8, 7)
        ])
        self.assertEqual(list(self.client.generate_clauses("Hello")), ["Hark!", "Onward."])
        self.safeguard.record_usage.assert_called_once_with(total_tokens=15, prompt_tokens=8, candidate_tokens=7)
        self.assertIs(self.client._genai_client, self.sdk)
        config = self.sdk.models.generate_content_stream.call_args.kwargs["config"]
        self.assertEqual(config["thinking_config"], {"thinking_level": "MINIMAL"})
        self.assertEqual(config["max_output_tokens"], 128)
        self.assertEqual(self.sdk.models.generate_content_stream.call_args.kwargs["model"], "gemini-3.5-flash-lite")

    def test_explicit_legacy_flash_model_disables_thinking_with_budget(self):
        self.client.text_model_name = "gemini-2.5-flash"
        self.sdk.models.generate_content_stream.return_value = [self.chunk("Onward!")]
        self.client.generate_response("Hello")
        config = self.sdk.models.generate_content_stream.call_args.kwargs["config"]
        self.assertEqual(config["thinking_config"], {"thinking_budget": 0})

    def test_history_preserves_roles_and_limits_turns(self):
        self.sdk.models.generate_content_stream.return_value = [self.chunk("Onward!")]
        history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "old answer"},
                   {"role": "user", "content": "recent"}, {"role": "assistant", "content": "recent answer"}]
        self.client.generate_response("Now", history, "Override persona")
        call = self.sdk.models.generate_content_stream.call_args.kwargs
        self.assertEqual([item["role"] for item in call["contents"]], ["user", "model", "user"])
        self.assertEqual(call["contents"][0]["parts"], [{"text": "recent"}])
        self.assertEqual(call["config"]["system_instruction"], "Override persona")

    def test_zero_history_does_not_send_entire_conversation(self):
        self.client.history_turn_limit = 0
        self.assertEqual(self.client._contents("Now", [{"role": "user", "content": "old"}]),
                         [{"role": "user", "parts": [{"text": "Now"}]}])

    def test_error_enters_cooldown_for_fast_local_fallback(self):
        self.sdk.models.generate_content_stream.side_effect = TimeoutError("network unavailable")
        with self.assertRaises(TimeoutError):
            self.client.generate_response("Hello")
        self.assertFalse(self.client.is_available()[0])
        with self.assertRaises(RuntimeError):
            self.client.generate_response("Hello again")
        self.sdk.models.generate_content_stream.assert_called_once()

    def test_empty_response_requests_fallback(self):
        self.sdk.models.generate_content_stream.return_value = [self.chunk(None, 8, 8)]
        with self.assertRaisesRegex(RuntimeError, "no spoken text"):
            self.client.generate_response("Hello")
        self.safeguard.record_usage.assert_called_once_with(total_tokens=8, prompt_tokens=8, candidate_tokens=0)

    def test_partial_stream_closes_and_records_usage_on_cancellation(self):
        closed = []

        def source():
            try:
                yield self.chunk("Hark! ", 10, 8, 2)
                yield self.chunk("Onward!", 12, 8, 4)
            finally:
                closed.append(True)

        self.sdk.models.generate_content_stream.return_value = source()
        clauses = self.client.generate_clauses("Hello")
        self.assertEqual(next(clauses), "Hark!")
        clauses.close()
        self.assertEqual(closed, [True])
        self.safeguard.record_usage.assert_called_once_with(total_tokens=10, prompt_tokens=8, candidate_tokens=2)

    def test_partial_stream_error_is_exposed_without_repeating_text(self):
        def source():
            yield self.chunk("Onward!", 10, 8, 2)
            raise TimeoutError("lost connection")

        self.sdk.models.generate_content_stream.return_value = source()
        stream = self.client.generate_response_stream("Hello")
        self.assertEqual(next(stream), "Onward!")
        with self.assertRaises(TimeoutError):
            next(stream)
        self.safeguard.record_usage.assert_called_once_with(total_tokens=10, prompt_tokens=8, candidate_tokens=2)

    def test_sdk_serializes_generation_and_decodes_sse_without_network(self):
        try:
            import httpx
            from google import genai
        except ImportError:
            self.skipTest("Optional google-genai SDK is not installed")

        requests_seen = []

        def respond(request):
            requests_seen.append(json.loads(request.content))
            event = {
                "candidates": [{"content": {"role": "model", "parts": [{"text": "Onward!"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"totalTokenCount": 12, "promptTokenCount": 8, "candidatesTokenCount": 4},
            }
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text="data: " + json.dumps(event) + "\n\n")

        transport_client = httpx.Client(transport=httpx.MockTransport(respond))
        sdk = genai.Client(api_key="test-only", http_options={"httpx_client": transport_client, "retry_options": {"attempts": 1}})
        self.addCleanup(sdk.close)
        self.client._genai_client = sdk
        self.assertEqual(self.client.generate_response("Hello"), "Onward!")
        self.assertEqual(requests_seen[0]["contents"], [{"parts": [{"text": "Hello"}], "role": "user"}])
        thinking = requests_seen[0]["generationConfig"]["thinkingConfig"]
        self.assertEqual(thinking.get("thinkingLevel", thinking.get("thinking_level")), "MINIMAL")
        self.safeguard.record_usage.assert_called_once_with(total_tokens=12, prompt_tokens=8, candidate_tokens=4)

    def test_close_releases_sdk_connections(self):
        self.client.close()
        self.sdk.close.assert_called_once()
        self.assertFalse(self.client.is_available()[0])

    @staticmethod
    def live_message(audio=None, complete=False, total=0, output=0):
        model_turn = None if audio is None else SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=audio))])
        return SimpleNamespace(
            usage_metadata=SimpleNamespace(total_token_count=total, response_token_count=output),
            server_content=SimpleNamespace(model_turn=model_turn, interrupted=False, input_transcription=None,
                                           output_transcription=None, turn_complete=complete),
        )

    def live_session(self, messages):
        session = MagicMock()
        session.send_client_content = AsyncMock()
        session.send_realtime_input = AsyncMock()

        async def receive():
            for message in messages:
                yield message

        session.receive.side_effect = receive
        self.sdk.aio.live.connect.return_value.__aenter__.return_value = session
        return session

    def test_native_voice_and_history_are_sent_with_explicit_turn_boundary(self):
        session = self.live_session([self.live_message(b"pcm", total=5), self.live_message(complete=True, total=9, output=4)])
        audio = Mock()
        history = [{"role": "user", "content": "previous"}, {"role": "assistant", "content": "previous reply"}]
        self.assertTrue(self.client.execute_turn("Hello", audio, conversation_history=history))
        audio.assert_called_once_with(b"pcm")
        sent = session.send_client_content.call_args.kwargs
        self.assertTrue(sent["turn_complete"])
        self.assertEqual(len(sent["turns"]), 3)
        config = self.sdk.aio.live.connect.call_args.kwargs["config"]
        self.assertEqual(config["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"], "Charon")
        self.assertIn("output_audio_transcription", config)
        self.safeguard.record_usage.assert_called_once_with(total_tokens=9, prompt_tokens=0, candidate_tokens=4)

    def test_native_empty_or_incomplete_response_requests_fallback(self):
        self.live_session([self.live_message(complete=True)])
        self.assertFalse(self.client.execute_turn("Hello", Mock()))
        self.live_session([self.live_message(b"partial")])
        self.assertFalse(self.client.execute_turn("Hello", Mock()))

    def test_native_timeout_releases_session(self):
        session = self.live_session([])

        async def stalled():
            await asyncio.sleep(1)
            yield self.live_message(complete=True)

        session.receive.side_effect = stalled
        self.client.turn_timeout = 0.01
        self.assertFalse(self.client.execute_turn("Hello", Mock()))
        self.sdk.aio.live.connect.return_value.__aexit__.assert_awaited_once()
        self.assertFalse(self.client._is_connected)


if __name__ == "__main__":
    unittest.main()
