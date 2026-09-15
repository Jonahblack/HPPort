"""Token Usage Safeguard and Budget Manager for Gemini Live API.

Tracks bidirectional streaming token consumption against user-defined free tier
quotas, persists daily history across reboots, and enforces an immediate cutoff
and fallback to the local offline pipeline when limits are approached or reached.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple


class TokenSafeguard:
    """Thread-safe persistent token tracker and quota enforcer."""

    DEFAULT_DAILY_LIMIT = 250_000  # Default safe daily token ceiling
    DEFAULT_SESSION_LIMIT = 40_000  # Default per-visitor session ceiling

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        live_cfg = cfg.get("gemini_live", {})
        hardware_cfg = cfg.get("hardware", {})

        self.enabled = bool(live_cfg.get("enabled", True))
        self.daily_limit = int(live_cfg.get("max_daily_tokens", self.DEFAULT_DAILY_LIMIT))
        self.session_limit = int(live_cfg.get("max_session_tokens", self.DEFAULT_SESSION_LIMIT))
        self.fallback_speech = live_cfg.get(
            "quota_fallback_text",
            "My celestial communications are depleted for today! I shall converse with thee through local enchantments instead.",
        )

        # Storage directory
        cache_dir = hardware_cfg.get("cache_dir", "./cache")
        storage_file = live_cfg.get("storage_file", "token_usage.json")
        self.storage_path = os.path.join(cache_dir, storage_file)

        self._lock = threading.Lock()
        self.session_tokens = 0
        self.session_turns = 0
        self.current_date = self._utc_today_string()
        self.daily_tokens = 0
        self.daily_turns = 0
        self.all_time_tokens = 0

        self._load_state()

    @staticmethod
    def _utc_today_string() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def _check_day_rollover_locked(self) -> None:
        """Reset daily counters if a new UTC day has started."""
        today = self._utc_today_string()
        if today != self.current_date:
            print(f"[Safeguard] UTC day rolled over ({self.current_date} -> {today}). Resetting daily token counter.")
            self.current_date = today
            self.daily_tokens = 0
            self.daily_turns = 0
            self._save_state_locked()

    def _load_state(self) -> None:
        with self._lock:
            if not os.path.exists(self.storage_path):
                return

            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                saved_date = data.get("date", "")
                today = self._utc_today_string()
                self.all_time_tokens = int(data.get("all_time_tokens", 0))

                if saved_date == today:
                    self.current_date = today
                    self.daily_tokens = int(data.get("daily_tokens", 0))
                    self.daily_turns = int(data.get("daily_turns", 0))
                    print(
                        f"[Safeguard] Restored usage for {today}: "
                        f"{self.daily_tokens:,} / {self.daily_limit:,} tokens used ({self.daily_turns} turns)."
                    )
                else:
                    self.current_date = today
                    self.daily_tokens = 0
                    self.daily_turns = 0
                    print(f"[Safeguard] Starting fresh daily quota window for {today}.")
                    self._save_state_locked()
            except Exception as exc:
                print(f"[Safeguard] Notice: Failed to load {self.storage_path} ({exc}). Using fresh counters.")

    def _save_state_locked(self) -> None:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.storage_path)), exist_ok=True)
            payload = {
                "date": self.current_date,
                "daily_tokens": self.daily_tokens,
                "daily_turns": self.daily_turns,
                "all_time_tokens": self.all_time_tokens,
                "daily_limit": self.daily_limit,
                "session_limit": self.session_limit,
                "last_updated": time.time(),
            }
            temp_path = f"{self.storage_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_path, self.storage_path)
        except Exception as exc:
            print(f"[Safeguard] Warning: Failed to persist token state: {exc}")

    def can_use_live_api(self) -> Tuple[bool, str]:
        """Check if Gemini Live API is permitted under current token budgets."""
        if not self.enabled:
            return False, "Gemini Live is disabled in configuration"

        with self._lock:
            self._check_day_rollover_locked()

            if self.daily_tokens >= self.daily_limit:
                pct = (self.daily_tokens / max(1, self.daily_limit)) * 100.0
                return False, f"Daily token ceiling reached ({self.daily_tokens:,}/{self.daily_limit:,}, {pct:.0f}%)"

            if self.session_tokens >= self.session_limit:
                return False, f"Visitor session ceiling reached ({self.session_tokens:,}/{self.session_limit:,})"

            return True, "OK"

    def record_usage(
        self,
        total_tokens: int,
        prompt_tokens: int = 0,
        candidate_tokens: int = 0,
    ) -> None:
        """Record token usage reported by Gemini Live usageMetadata."""
        if total_tokens <= 0:
            return

        with self._lock:
            self._check_day_rollover_locked()

            # For incremental updates or cumulative turn totals:
            self.session_tokens += total_tokens
            self.daily_tokens += total_tokens
            self.all_time_tokens += total_tokens
            self.daily_turns += 1
            self.session_turns += 1

            pct = (self.daily_tokens / max(1, self.daily_limit)) * 100.0
            print(
                f"[Safeguard] Recorded {total_tokens:,} tokens "
                f"(Day: {self.daily_tokens:,}/{self.daily_limit:,} [{pct:.1f}%] | "
                f"Session: {self.session_tokens:,}/{self.session_limit:,})"
            )

            self._save_state_locked()

            if self.daily_tokens >= self.daily_limit:
                print(f"[Safeguard] WARNING: Daily token quota EXCEEDED! Switching to local offline mode.")

    def reset_session(self) -> None:
        """Reset per-visitor session token counter (e.g. on return to IDLE/COOLDOWN)."""
        with self._lock:
            if self.session_tokens > 0:
                print(f"[Safeguard] Resetting visitor session tokens (was {self.session_tokens:,} across {self.session_turns} turns).")
            self.session_tokens = 0
            self.session_turns = 0

    def get_metrics(self) -> Dict[str, Any]:
        """Expose current token budget statistics for HUD and status plate rendering."""
        with self._lock:
            self._check_day_rollover_locked()
            pct = (self.daily_tokens / max(1, self.daily_limit)) * 100.0
            is_locked = self.daily_tokens >= self.daily_limit or self.session_tokens >= self.session_limit
            remaining = max(0, self.daily_limit - self.daily_tokens)

            return {
                "enabled": self.enabled,
                "daily_used": self.daily_tokens,
                "daily_limit": self.daily_limit,
                "daily_percent": pct,
                "daily_remaining": remaining,
                "session_used": self.session_tokens,
                "session_limit": self.session_limit,
                "is_locked": is_locked,
                "status_text": "EXCEEDED" if is_locked else ("SAFE" if pct < 80 else "WARNING"),
            }
