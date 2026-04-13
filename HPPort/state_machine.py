from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, Optional


class PortraitState(str, Enum):
    IDLE = "IDLE"
    WAKE_PENDING = "WAKE_PENDING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    COOLDOWN = "COOLDOWN"


@dataclass
class PortraitStateMachine:
    state: PortraitState = PortraitState.IDLE
    state_since: float = field(default_factory=time.monotonic)
    context: Dict[str, Any] = field(default_factory=dict)

    def transition(self, new_state: PortraitState, **context: Any) -> None:
        self.state = new_state
        self.state_since = time.monotonic()
        self.context = context

    def seconds_in_state(self) -> float:
        return time.monotonic() - self.state_since

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return self.context.get(key, default)
