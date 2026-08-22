"""
llama.cpp HTTP API Client for Gemma 4 E2B Instruct on Raspberry Pi 5 / Desktop.
Communicates with a persistent llama-server instance (e.g. running on port 8080).
Supports low-latency streaming and performance telemetry.
"""

import json
import logging
import time
from typing import Dict, Generator, List, Optional
import urllib.error
import urllib.request

from .base import BaseLLMClient, LLMMetrics, LLMResponse

logger = logging.getLogger(__name__)


class LlamaClient(BaseLLMClient):
    """Client for local llama.cpp server running Gemma 4 E2B Instruct."""

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:8080/v1/chat/completions",
        model_name: str = "gemma-4-e2b-instruct",
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 150,
        timeout_seconds: float = 15.0,
    ):
        super().__init__(system_prompt=system_prompt)
        self.endpoint_url = endpoint_url
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def health_check(self) -> bool:
        """Check if llama.cpp server is reachable."""
        try:
            health_url = self.endpoint_url.replace("/v1/chat/completions", "/health")
            req = urllib.request.Request(health_url, headers={"User-Agent": "TalkingPortrait/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            logger.warning("llama.cpp health check failed at %s: %s", self.endpoint_url, e)
            return False

    def _build_payload(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None, stream: bool = False) -> Dict:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if conversation_history:
            # Keep recent turns to avoid unbounded context
            for msg in conversation_history[-6:]:
                messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        messages.append({"role": "user", "content": prompt})

        return {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    def generate(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> LLMResponse:
        """Generate response synchronously."""
        payload = self._build_payload(prompt, conversation_history, stream=False)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "TalkingPortrait/1.0"},
        )

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                duration = time.time() - start_time
                content = resp_json["choices"][0]["message"]["content"].strip()
                tokens = resp_json.get("usage", {}).get("completion_tokens", max(1, len(content.split())))

                metrics = LLMMetrics(
                    time_to_first_token_seconds=duration * 0.4,
                    total_generation_seconds=duration,
                    tokens_generated=tokens,
                    tokens_per_second=tokens / max(0.001, duration),
                )
                logger.info("Gemma generated %d tokens in %.2fs (%.1f tok/s)", tokens, duration, metrics.tokens_per_second)
                return LLMResponse(text=content, metrics=metrics)
        except Exception as e:
            logger.error("LlamaClient request failed: %s", e)
            return LLMResponse(
                text="The magical energy in the castle wanes... speak again, friend!",
                metrics=LLMMetrics(total_generation_seconds=time.time() - start_time),
            )

    def generate_stream(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Generator[str, None, LLMResponse]:
        """Stream chunks from llama.cpp server for low-latency first-phrase TTS."""
        payload = self._build_payload(prompt, conversation_history, stream=True)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "TalkingPortrait/1.0"},
        )

        start_time = time.time()
        first_token_time: Optional[float] = None
        full_text = []
        token_count = 0

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str or line_str == "data: [DONE]":
                        continue
                    if line_str.startswith("data: "):
                        raw_json = line_str[6:]
                        try:
                            chunk = json.loads(raw_json)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                if first_token_time is None:
                                    first_token_time = time.time() - start_time
                                full_text.append(content)
                                token_count += 1
                                yield content
                        except Exception:
                            continue
        except Exception as e:
            logger.error("LlamaClient streaming error: %s", e)
            fallback = "Indeed, the portrait listens!"
            yield fallback
            full_text.append(fallback)

        total_time = time.time() - start_time
        metrics = LLMMetrics(
            time_to_first_token_seconds=first_token_time or total_time,
            total_generation_seconds=total_time,
            tokens_generated=token_count,
            tokens_per_second=token_count / max(0.001, total_time),
        )
        return LLMResponse(text="".join(full_text), metrics=metrics)
