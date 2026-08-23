"""Llama.cpp client driver connecting to OpenAI-compatible REST server (Gemma 4)."""

import time
import requests
from typing import List, Dict, Any, Optional
from llm.base import BaseLLMClient


class LlamaClient(BaseLLMClient):
    """Client for local llama-server running Gemma 4 E2B Instruct on Raspberry Pi 5."""

    def __init__(self, config: Dict[str, Any]):
        llm_cfg = config.get("llm", {})
        self.endpoint_url = llm_cfg.get("endpoint_url", "http://127.0.0.1:8080/v1/chat/completions")
        self.model_name = llm_cfg.get("model_name", "gemma-4-e2b-instruction")
        self.temperature = float(llm_cfg.get("temperature", 0.7))
        self.max_tokens = int(llm_cfg.get("max_tokens", 150))
        self.system_prompt = llm_cfg.get(
            "system_prompt",
            "You are Lord Cadogan, an eccentric knight in a magical portrait. Speak boldly in 1-3 short sentences.",
        )
        self.timeout = 15.0

    def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        sys_prompt = system_prompt or self.system_prompt
        messages = [{"role": "system", "content": sys_prompt}]

        if conversation_history:
            for item in conversation_history[-6:]:
                role = item.get("role", "user")
                if role in ("user", "assistant", "system"):
                    messages.append({"role": role, "content": item.get("content", "")})

        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        start_time = time.time()
        try:
            resp = requests.post(self.endpoint_url, json=payload, timeout=self.timeout)
            duration = time.time() - start_time

            if resp.status_code == 200:
                data = resp.json()
                reply = data["choices"][0]["message"]["content"].strip()
                print(f"[LLM] Gemma 4 completed in {duration:.2f}s: \"{reply}\"")
                return reply
            else:
                print(f"[LLM] Server returned HTTP {resp.status_code}: {resp.text}")
                return "By my troth, a mystical perturbation clouds my mind! Ask again, brave soul!"
        except requests.exceptions.RequestException as e:
            print(f"[LLM] Connection error to {self.endpoint_url}: {e}")
            return "Hark! The castle magical currents are severed. Check that llama-server is awake!"
