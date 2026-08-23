"""Mock LLM client driver for desktop demo mode and unit testing."""

import random
from typing import List, Dict, Any, Optional
from llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Provides scripted, in-character Lord Cadogan responses for desktop testing."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.canned_responses = [
            "Stand and deliver! If thou seekest passage through this corridor, prepare for a duel of wits!",
            "By Merlin's beard! I once wrestled a three-headed Wyvern atop the Astronomy Tower with nought but a butter knife!",
            "Speak plainly, knave! A true knight of the Round Table waits for no rambling mortal!",
            "Ah, a bold adventurer! Dost thou pledge thine honor to defend Hogwarts against the dark arts?",
            "Forward, to glory! No obstacle shall deter Sir Cadogan and his trusty steed!",
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
            return "I am Sir Cadogan, knight of the realm, slayer of monsters, and proud defender of this hallowed frame!"
        if "password" in lower or "secret" in lower:
            return "The password is 'Caput Draconis'! Or was it 'Oddsbodikins'? No matter, only the valiant shall pass!"
        if "dragon" in lower or "quest" in lower:
            return "A quest! Mount your steed, brandish your blade, and let us ride into legend!"

        return random.choice(self.canned_responses)
