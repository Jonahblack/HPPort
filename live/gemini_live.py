"""Gemini text streaming for a consistent local voice, plus optional Live audio."""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from live.safeguard import TokenSafeguard
from llm.base import BaseLLMClient


class GeminiLiveClient(BaseLLMClient):
    """Reuse the SDK's HTTP pool for text; isolate optional Live audio turns."""

    DEFAULT_MODEL = "gemini-3.1-flash-live-preview"
    DEFAULT_TEXT_MODEL = "gemini-3.5-flash-lite"
    DEFAULT_VOICE = "Charon"

    def __init__(self, config: Dict[str, Any], safeguard: Optional[TokenSafeguard] = None):
        self.config = config
        self.live_cfg = config.get("gemini_live", {})
        self.llm_cfg = config.get("llm", {})
        self.model_name = self.live_cfg.get("model", self.DEFAULT_MODEL)
        self.text_model_name = self.live_cfg.get("text_model", self.DEFAULT_TEXT_MODEL)
        self.voice_name = self.live_cfg.get("voice_name", self.DEFAULT_VOICE)
        self.api_key_env = self.live_cfg.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "").strip()
        self.timeout = max(1.0, float(self.live_cfg.get("timeout_seconds", 12.0)))
        self.turn_timeout = max(1.0, float(self.live_cfg.get("turn_timeout_seconds", 30.0)))
        self.retry_cooldown = max(0.0, float(self.live_cfg.get("retry_cooldown_seconds", 30.0)))
        self.history_turn_limit = max(0, int(self.llm_cfg.get("history_turn_limit", 4)))
        self.safeguard = safeguard or TokenSafeguard(config)
        self.system_prompt = self.llm_cfg.get(
            "system_prompt",
            "You are Lord Cadogan, a bold eccentric knight and noble warrior living inside an enchanted Hogwarts portrait. Speak boldly in one lively spoken sentence under 20 words.",
        )
        self._is_connected = False
        self._last_error = ""
        self._retry_after = 0.0
        self._genai_client = None
        self._init_sdk()

    def _init_sdk(self) -> None:
        if not self.api_key:
            self._last_error = f"Environment variable {self.api_key_env} is not set"
            return
        try:
            from google import genai  # type: ignore

            self._genai_client = genai.Client(
                api_key=self.api_key,
                http_options={
                    "timeout": int(self.timeout * 1000),
                    # Let the local model answer instead of hiding retries/backoff.
                    "retry_options": {"attempts": 1},
                },
            )
        except ImportError:
            self._last_error = "google-genai package is not installed (run: pip install google-genai)"
        except Exception as exc:
            self._last_error = f"SDK initialization error: {exc}"

    def close(self) -> None:
        """Release pooled HTTP connections after conversation workers stop."""
        if self._genai_client is not None:
            self._genai_client.close()
            self._genai_client = None

    def is_available(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, f"API key not set (${self.api_key_env})"
        if self._genai_client is None:
            return False, self._last_error or "SDK not initialized"
        if time.monotonic() < self._retry_after:
            return False, "Gemini temporarily unavailable; local conversation is active"
        return self.safeguard.can_use_live_api()

    def _mark_failure(self, exc: Exception) -> None:
        self._last_error = str(exc)
        self._retry_after = time.monotonic() + self.retry_cooldown

    def _contents(self, user_message: Optional[str], history: Optional[List[Dict[str, str]]]) -> list:
        contents = []
        # [-0:] means *all* entries in Python, so handle disabled history explicitly.
        if history and self.history_turn_limit:
            valid = [item for item in history if item.get("role") in ("user", "assistant") and item.get("content")]
            for item in valid[-2 * self.history_turn_limit:]:
                contents.append({
                    "role": "model" if item["role"] == "assistant" else "user",
                    "parts": [{"text": item["content"]}],
                })
        if user_message is not None:
            contents.append({"role": "user", "parts": [{"text": user_message}]})
        return contents

    @staticmethod
    def _usage_counts(usage: Any) -> Tuple[int, int, int]:
        # Text generation and Live expose the same count under different names.
        output = getattr(usage, "candidates_token_count", None)
        if output is None:
            output = getattr(usage, "response_token_count", 0)
        return (int(getattr(usage, "total_token_count", 0) or 0),
                int(getattr(usage, "prompt_token_count", 0) or 0), int(output or 0))

    def _record_usage(self, counts: Tuple[int, int, int]) -> None:
        if counts[0]:
            self.safeguard.record_usage(
                total_tokens=counts[0], prompt_tokens=counts[1], candidate_tokens=counts[2]
            )

    def generate_response(self, user_message, conversation_history=None, system_prompt=None) -> str:
        return "".join(self.generate_response_stream(user_message, conversation_history, system_prompt)).strip()

    def generate_response_stream(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Iterator[str]:
        """Yield text for Piper; errors propagate so callers can choose fallback.

        Streaming usage snapshots are cumulative. Persist only the latest totals,
        once per turn, including when a consumer closes a partly consumed stream.
        """
        can_use, reason = self.is_available()
        if not can_use:
            raise RuntimeError(reason)
        generation_config = {
            "system_instruction": system_prompt or self.system_prompt,
            "temperature": float(self.llm_cfg.get("temperature", 0.7)),
            "max_output_tokens": int(self.live_cfg.get("max_output_tokens", 128)),
            "automatic_function_calling": {"disable": True},
        }
        if self.llm_cfg.get("disable_reasoning", True):
            if self.text_model_name == "gemini-3.5-flash-lite":
                generation_config["thinking_config"] = {"thinking_level": "MINIMAL"}
            elif self.text_model_name.startswith("gemini-2.5-flash"):
                # Retain configured legacy models for existing API users.
                generation_config["thinking_config"] = {"thinking_budget": 0}
        usage = (0, 0, 0)
        stream = None
        has_text = False
        started = time.monotonic()
        try:
            stream = self._genai_client.models.generate_content_stream(
                model=self.text_model_name,
                contents=self._contents(user_message, conversation_history),
                config=generation_config,
            )
            for chunk in stream:
                counts = self._usage_counts(getattr(chunk, "usage_metadata", None))
                usage = tuple(max(old, new) for old, new in zip(usage, counts))
                text = chunk.text
                if text:
                    if not has_text:
                        print(f"[Gemini] First text in {time.monotonic() - started:.2f}s")
                    has_text = True
                    yield text
            if not has_text:
                raise RuntimeError("Gemini returned no spoken text")
        except Exception as exc:
            self._mark_failure(exc)
            raise
        finally:
            self._record_usage(usage)
            close = getattr(stream, "close", None)
            if close:
                close()

    async def execute_turn_async(
        self,
        user_input: str | List[bytes],
        on_audio_chunk: Callable[[bytes], None],
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_interrupted: Optional[Callable[[], None]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> bool:
        """Run optional native speech, bounded by a complete-turn timeout.

        Audio callbacks must enqueue PCM and return promptly, so network receive
        and playback can run concurrently. Returns False on incomplete turns.
        """
        can_use, reason = self.is_available()
        if not can_use:
            print(f"[GeminiLive] Unavailable: {reason}")
            return False
        try:
            return await asyncio.wait_for(
                self._receive_live_turn(user_input, on_audio_chunk, on_transcript, on_interrupted, conversation_history),
                timeout=self.turn_timeout,
            )
        except Exception as exc:
            self._mark_failure(exc)
            print(f"[GeminiLive] Turn failed ({type(exc).__name__}: {exc}).")
            return False
        finally:
            self._is_connected = False

    async def _receive_live_turn(self, user_input, on_audio_chunk, on_transcript, on_interrupted, history) -> bool:
        live_config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": self.system_prompt,
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": self.voice_name}}},
        }
        usage = (0, 0, 0)
        try:
            async with self._genai_client.aio.live.connect(model=self.model_name, config=live_config) as session:
                self._is_connected = True
                if isinstance(user_input, str):
                    await session.send_client_content(turns=self._contents(user_input, history), turn_complete=True)
                else:
                    context = self._contents(None, history)
                    if context:
                        await session.send_client_content(turns=context, turn_complete=False)
                    for chunk in user_input:
                        await session.send_realtime_input(audio={"data": chunk, "mime_type": "audio/pcm;rate=16000"})
                    await session.send_realtime_input(audio_stream_end=True)

                completed = False
                has_audio = False
                async for message in session.receive():
                    counts = self._usage_counts(getattr(message, "usage_metadata", None))
                    usage = tuple(max(old, new) for old, new in zip(usage, counts))
                    content = message.server_content
                    if not content:
                        continue
                    if content.interrupted and on_interrupted:
                        on_interrupted()
                    if on_transcript:
                        for role, transcription in (("user", content.input_transcription), ("assistant", content.output_transcription)):
                            if transcription and transcription.text:
                                on_transcript(role, transcription.text)
                    if content.model_turn:
                        for part in content.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                audio = part.inline_data.data
                                on_audio_chunk(base64.b64decode(audio) if isinstance(audio, str) else audio)
                                has_audio = True
                    if content.turn_complete:
                        completed = True
                        break
                return completed and has_audio
        finally:
            self._record_usage(usage)

    def execute_turn(
        self,
        user_input: str | List[bytes],
        on_audio_chunk: Callable[[bytes], None],
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_interrupted: Optional[Callable[[], None]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> bool:
        """Synchronous entry point for the conversation worker."""
        return asyncio.run(self.execute_turn_async(
            user_input, on_audio_chunk, on_transcript, on_interrupted, conversation_history
        ))
