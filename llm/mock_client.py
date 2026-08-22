"""
Mock LLM client for desktop development and automated testing.
Provides fast, predictable, scripted, or random responses mimicking Gemma 4.
"""

import logging
import random
import time
from typing import Dict, Generator, List, Optional

from .base import BaseLLMClient, LLMMetrics, LLMResponse

logger = logging.getLogger(__name__)


class MockLLMClient(BaseLLMClient):
    """Simulated Gemma 4 client for rapid desktop development."""

    PRESET_RESPONSES = [
        "Aha! A curious wanderer in my gallery! Tell me, what magic brings you to my hall?",
        "Halt! By the chivalric code of Cadogan, you stand before greatness. How fares the kingdom today?",
        "The candles flicker in the draft, but my sword arm remains swift. Speak your quest!",
        "Never fear! A knight of portraiture is always ready for conversation. What news from outside?",
        "Indeed, centuries on this canvas give one a grand perspective on the mysteries of the castle.",
    ]

    def __init__(self, system_prompt: str = "", artificial_delay_seconds: float = 0.25):
        super().__init__(system_prompt=system_prompt)
        self.artificial_delay_seconds = artificial_delay_seconds

    def health_check(self) -> bool:
        return True

    def generate(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> LLMResponse:
        time.sleep(self.artificial_delay_seconds)
        text = random.choice(self.PRESET_RESPONSES)
        tokens = len(text.split())
        metrics = LLMMetrics(
            time_to_first_token_seconds=self.artificial_delay_seconds * 0.5,
            total_generation_seconds=self.artificial_delay_seconds,
            tokens_generated=tokens,
            tokens_per_second=tokens / max(0.01, self.artificial_delay_seconds),
        )
        return LLMResponse(text=text, metrics=metrics)

    def generate_stream(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Generator[str, None, LLMResponse]:
        text = random.choice(self.PRESET_RESPONSES)
        words = text.split(" ")
        start_time = time.time()
        first_token_time = 0.0

        for idx, word in enumerate(words):
            time.sleep(self.artificial_delay_seconds / max(1, len(words)))
            if idx == 0:
                first_token_time = time.time() - start_time
            yield word + (" " if idx < len(words) - 1 else "")

        total_time = time.time() - start_time
        metrics = LLMMetrics(
            time_to_first_token_seconds=first_token_time,
            total_generation_seconds=total_time,
            tokens_generated=len(words),
            tokens_per_second=len(words) / max(0.01, total_time),
        )
        return LLMResponse(text=text, metrics=metrics)
