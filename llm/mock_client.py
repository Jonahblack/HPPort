"""Mock LLM client driver for desktop demo mode and unit testing."""

import random
from typing import List, Dict, Any, Optional
from llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Provides scripted, in-character Wilhelm responses for desktop testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.canned_responses = [
            "Mind the copper coil on the bench! That little spark was entirely deliberate, I assure you.",
            "By the twin moons of Oakhaven! I haven't seen an astral alignment like this since my third expedition.",
            "A fascinating inquiry! Let me consult my celestial charts before the etheric resonance shifts.",
            "Welcome, friend! You arrive just as my miniature chronometer achieved perpetual balance.",
            "Every worthy invention requires two parts curiosity, one part courage, and perhaps a damp cloth for the smoke.",
        ]

    def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        # Check for keywords
        lower = user_message.lower()
        if "who are you" in lower or "name" in lower:
            return "I am Wilhelm, the Wandering Artificer—inventor, historian, and keeper of this enchanted workshop!"
        if "password" in lower or "secret" in lower:
            return "The password to my workshop vault is a trade secret, though a rare copper gear might loosen my tongue!"
        if "dragon" in lower or "quest" in lower or "expedition" in lower:
            return "An expedition! Gather your compass and charting tools, and let us map the unknown!"

        return random.choice(self.canned_responses)
