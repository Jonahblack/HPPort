"""Abstract base class for LLM conversation engines."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseLLMClient(ABC):
    """Abstract interface for LLM completion drivers."""

    @abstractmethod
    def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate conversational reply for the portrait.

        Args:
            user_message: Transcribed user speech.
            conversation_history: List of past turn dictionaries (e.g. [{'role': 'user', 'content': '...'}, ...]).
            system_prompt: Persona system instruction override.

        Returns:
            The generated in-character dialogue string.
        """
        pass
