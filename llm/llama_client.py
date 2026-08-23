"""Llama.cpp client driver connecting to OpenAI-compatible REST server (Gemma 4)."""

import time
import requests
from typing import List, Dict, Any, Optional
from llm.base import BaseLLMClient


class LlamaClient(BaseLLMClient):
    """Client for local llama-server running Gemma 4 E2B Instruct on Raspberry Pi 5."""

    def __init__(self, config: Dict[str, Any]):
        llm_cfg = config.get("llm", {})
        self.endpoint_url = self._normalize_endpoint_url(
            llm_cfg.get("endpoint_url", "http://127.0.0.1:8080/v1/chat/completions")
        )
        self.model_name = llm_cfg.get("model_name", "gemma-4-e2b-instruction")
        self.temperature = float(llm_cfg.get("temperature", 0.7))
        self.max_tokens = int(llm_cfg.get("max_tokens", 150))
        self.timeout = float(llm_cfg.get("timeout_seconds", 90.0))
        self.connect_timeout = float(llm_cfg.get("connect_timeout_seconds", 5.0))
        self.history_turn_limit = int(llm_cfg.get("history_turn_limit", 4))
        self._resolved_model_name: Optional[str] = None
        self.system_prompt = llm_cfg.get(
            "system_prompt",
            "You are Lord Cadogan, an eccentric knight in a magical portrait. Speak boldly in 1-3 short sentences.",
        )

    @staticmethod
    def _normalize_endpoint_url(endpoint_url: str) -> str:
        trimmed = endpoint_url.rstrip("/")
        if trimmed.endswith("/v1/chat/completions"):
            return trimmed
        if "/v1/" in trimmed:
            return trimmed
        return f"{trimmed}/v1/chat/completions"

    def _models_endpoint(self) -> str:
        return self.endpoint_url.rsplit("/chat/completions", 1)[0] + "/models"

    def _extract_model_candidates(self, payload: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for key in ("data", "models"):
            entries = payload.get(key, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                model_id = entry.get("id") or entry.get("model") or entry.get("name")
                if isinstance(model_id, str) and model_id not in candidates:
                    candidates.append(model_id)
                aliases = entry.get("aliases", [])
                if isinstance(aliases, list):
                    for alias in aliases:
                        if isinstance(alias, str) and alias not in candidates:
                            candidates.append(alias)
        return candidates

    def _resolve_model_name(self) -> str:
        if self._resolved_model_name:
            return self._resolved_model_name

        requested = self.model_name
        try:
            resp = requests.get(
                self._models_endpoint(),
                timeout=(self.connect_timeout, min(self.timeout, 15.0)),
            )
            if resp.status_code != 200:
                self._resolved_model_name = requested
                return requested

            candidates = self._extract_model_candidates(resp.json())
            if not candidates:
                self._resolved_model_name = requested
                return requested

            if requested in candidates:
                self._resolved_model_name = requested
                return requested

            for candidate in candidates:
                if candidate.endswith(requested):
                    self._resolved_model_name = candidate
                    print(f"[LLM] Resolved model '{requested}' -> '{candidate}'")
                    return candidate

            partial_matches = [candidate for candidate in candidates if requested in candidate]
            if len(partial_matches) == 1:
                self._resolved_model_name = partial_matches[0]
                print(f"[LLM] Resolved model '{requested}' -> '{partial_matches[0]}'")
                return partial_matches[0]

            if len(candidates) == 1:
                self._resolved_model_name = candidates[0]
                print(f"[LLM] Using sole available model '{candidates[0]}'")
                return candidates[0]
        except requests.exceptions.RequestException as exc:
            print(f"[LLM] Model discovery notice: {exc}")

        self._resolved_model_name = requested
        return requested

    def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        sys_prompt = system_prompt or self.system_prompt
        messages = [{"role": "system", "content": sys_prompt}]

        if conversation_history:
            max_history_messages = max(0, self.history_turn_limit * 2)
            for item in conversation_history[-max_history_messages:]:
                role = item.get("role", "user")
                if role in ("user", "assistant", "system"):
                    messages.append({"role": role, "content": item.get("content", "")})

        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self._resolve_model_name(),
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "n_predict": self.max_tokens,
            "stream": False,
        }

        start_time = time.time()
        try:
            resp = requests.post(
                self.endpoint_url,
                json=payload,
                timeout=(self.connect_timeout, self.timeout),
            )
            duration = time.time() - start_time

            if resp.status_code == 200:
                data = resp.json()
                reply = data["choices"][0]["message"]["content"].strip()
                print(f"[LLM] Gemma 4 completed in {duration:.2f}s: \"{reply}\"")
                return reply
            else:
                print(f"[LLM] Server returned HTTP {resp.status_code}: {resp.text}")
                return "By my troth, a mystical perturbation clouds my mind! Ask again, brave soul!"
        except requests.exceptions.ReadTimeout:
            print(
                f"[LLM] Timed out waiting for llama-server after {self.timeout:.1f}s "
                f"(endpoint={self.endpoint_url})."
            )
            return "The castle oracle ponders too slowly just now. Keep llama-server running and allow a longer timeout!"
        except requests.exceptions.RequestException as e:
            print(f"[LLM] Connection error to {self.endpoint_url}: {e}")
            return "Hark! The castle magical currents are severed. Check that llama-server is awake!"
