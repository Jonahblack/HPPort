"""
Base abstract interface for LLM clients.
Defines clean contract for Gemma 4 and other language models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Dict, Generator, List, Optional


@dataclass
class LLMMetrics:
    time_to_first_token_seconds: float = 0.0
    total_generation_seconds: float = 0.0
    tokens_generated: int = 0
    tokens_per_second: float = 0.0


@dataclass
class LLMResponse:
    text: str
    metrics: LLMMetrics = field(default_factory=LLMMetrics)


class BaseLLMClient(ABC):
    """Abstract interface for local and remote LLM backends."""

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt

    @abstractmethod
    def generate(self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> LLMResponse:
        """Generate a complete text response synchronously."""
        pass

    @abstractmethod
    def generate_stream(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Generator[str, None, LLMResponse]:
        """Stream generated text token-by-token or phrase-by-phrase for low latency."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend server is reachable and ready."""
        pass
