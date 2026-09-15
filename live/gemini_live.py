"""Gemini Live API client for bidirectional real-time audio conversation.

Connects to Google Gemini Live API over WebSockets via google-genai SDK,
streaming 16kHz PCM mic audio directly and streaming 24kHz synthesized audio
and transcripts back to the portrait, while continuously reporting token
consumption to TokenSafeguard.
"""

from __future__ import annotations

import asyncio
import base64
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from live.safeguard import TokenSafeguard


class GeminiLiveClient:
    """Manages real-time bidirectional WebSocket sessions with Gemini Live API."""

    DEFAULT_MODEL = "gemini-3.1-flash-live-preview"
    DEFAULT_VOICE = "Puck"

    def __init__(self, config: Dict[str, Any], safeguard: Optional[TokenSafeguard] = None):
        self.config = config
        self.live_cfg = config.get("gemini_live", {})
        self.llm_cfg = config.get("llm", {})

        self.model_name = self.live_cfg.get("model", self.DEFAULT_MODEL)
        self.voice_name = self.live_cfg.get("voice_name", self.DEFAULT_VOICE)
        self.api_key_env = self.live_cfg.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "").strip()

        self.safeguard = safeguard or TokenSafeguard(config)
        self.system_prompt = self.llm_cfg.get(
            "system_prompt",
            "You are Lord Cadogan, a bold eccentric knight and noble warrior living inside an enchanted Hogwarts portrait. Speak boldly in one lively spoken sentence under 20 words.",
        )

        self._is_connected = False
        self._last_error = ""
        self._genai_client = None
        self._init_sdk()

    def _init_sdk(self) -> None:
        """Initialize Google GenAI client if package and API key are available."""
        if not self.api_key:
            self._last_error = f"Environment variable {self.api_key_env} is not set"
            return

        try:
            from google import genai  # type: ignore

            self._genai_client = genai.Client(api_key=self.api_key)
            print(f"[GeminiLive] Google GenAI SDK initialized (model='{self.model_name}', voice='{self.voice_name}').")
        except ImportError:
            self._last_error = "google-genai package is not installed (run: pip install google-genai)"
            print(f"[GeminiLive] Notice: {self._last_error}")
        except Exception as exc:
            self._last_error = f"SDK initialization error: {exc}"
            print(f"[GeminiLive] Notice: {self._last_error}")

    def is_available(self) -> Tuple[bool, str]:
        """Check if Live API is ready for use (SDK installed, key set, quota valid)."""
        if not self.api_key:
            return False, f"API key not set (${self.api_key_env})"

        if self._genai_client is None:
            return False, self._last_error or "SDK not initialized"

        can_use, reason = self.safeguard.can_use_live_api()
        if not can_use:
            return False, reason

        return True, "OK"

    async def execute_turn_async(
        self,
        user_input: str | List[bytes],
        on_audio_chunk: Callable[[bytes], None],
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_interrupted: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Execute a conversational speech turn over Gemini Live WebSockets.

        Args:
            user_input: Recognized text string OR list of 16kHz 16-bit mono PCM chunks from microphone.
            on_audio_chunk: Callback invoked when Gemini streams a 24kHz audio chunk back.
            on_transcript: Callback (role, text) for real-time user and assistant subtitles.
            on_interrupted: Callback invoked if user interrupts the portrait.

        Returns:
            True if turn completed successfully, False if fallback is needed.
        """
        can_use, reason = self.is_available()
        if not can_use:
            print(f"[GeminiLive] Cannot use Live API: {reason}. Triggering local fallback.")
            return False

        from google.genai import types  # type: ignore

        try:
            live_config = types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                system_instruction=types.Content(
                    parts=[types.Part(text=self.system_prompt)]
                ),
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice_name)
                    )
                ),
            )

            print(f"[GeminiLive] Connecting WebSocket session to {self.model_name}...")
            async with self._genai_client.aio.live.connect(
                model=self.model_name,
                config=live_config,
            ) as session:
                self._is_connected = True

                # 1. Send user input (Text or Audio Chunks)
                if isinstance(user_input, str):
                    await session.send_realtime_input(text=user_input)
                elif isinstance(user_input, list):
                    for chunk in user_input:
                        await session.send_realtime_input(
                            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                        )
                    await session.send_realtime_input(audio_stream_end=True)

                # 2. Receive streaming responses
                async for message in session.receive():
                    # Intercept token usage
                    if message.usage_metadata:
                        usage = message.usage_metadata
                        total_tok = getattr(usage, "total_token_count", 0) or 0
                        prompt_tok = getattr(usage, "prompt_token_count", 0) or 0
                        cand_tok = getattr(usage, "candidates_token_count", 0) or 0
                        if total_tok > 0:
                            self.safeguard.record_usage(
                                total_tokens=total_tok,
                                prompt_tokens=prompt_tok,
                                candidate_tokens=cand_tok,
                            )

                    content = message.server_content
                    if not content:
                        continue

                    if content.interrupted and on_interrupted:
                        on_interrupted()

                    if content.input_transcription and on_transcript:
                        on_transcript("user", content.input_transcription.text)

                    if content.output_transcription and on_transcript:
                        on_transcript("assistant", content.output_transcription.text)

                    if content.model_turn:
                        for part in content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                audio_bytes = part.inline_data.data
                                if isinstance(audio_bytes, str):
                                    audio_bytes = base64.b64decode(audio_bytes)
                                on_audio_chunk(audio_bytes)

                    # Turn complete signal
                    if content.turn_complete:
                        print("[GeminiLive] Model turn complete.")
                        break

                return True

        except Exception as exc:
            print(f"[GeminiLive] Live session exception ({exc}). Triggering local fallback.")
            self._last_error = str(exc)
            return False
        finally:
            self._is_connected = False

    def execute_turn(
        self,
        user_input: str | List[bytes],
        on_audio_chunk: Callable[[bytes], None],
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_interrupted: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Synchronous wrapper for execute_turn_async."""
        try:
            return asyncio.run(
                self.execute_turn_async(
                    user_input,
                    on_audio_chunk,
                    on_transcript,
                    on_interrupted,
                )
            )
        except Exception as exc:
            print(f"[GeminiLive] Sync wrapper error ({exc}).")
            return False
