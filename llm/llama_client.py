"""Llama.cpp client driver connecting to OpenAI-compatible REST server (Gemma 4)."""

import json
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
        self.max_tokens = int(llm_cfg.get("max_tokens", 24))
        self.timeout = float(llm_cfg.get("timeout_seconds", 90.0))
        self.connect_timeout = float(llm_cfg.get("connect_timeout_seconds", 5.0))
        self.history_turn_limit = int(llm_cfg.get("history_turn_limit", 4))
        self.cache_prompt = bool(llm_cfg.get("cache_prompt", True))
        self.disable_reasoning = bool(llm_cfg.get("disable_reasoning", True))
        self.empty_response_text = llm_cfg.get(
            "empty_response_text",
            "The castle spirits stole my answer. Ask once more, brave visitor!",
        )
        self._resolved_model_name: Optional[str] = None
        self.system_prompt = llm_cfg.get(
            "system_prompt",
            "You are Wilhelm, an eccentric knight in a magical portrait. Speak boldly in 1-3 short sentences.",
        )
        # Reuse TCP connections between discovery and conversational turns.
        self._session = requests.Session()

    def close(self) -> None:
        self._session.close()

    def _messages(self, user_message, conversation_history, system_prompt):
        messages = [{"role": "system", "content": system_prompt or self.system_prompt}]
        if conversation_history and self.history_turn_limit > 0:
            valid = [item for item in conversation_history if item.get("role") in ("user", "assistant")]
            messages.extend(
                {"role": item["role"], "content": item.get("content", "")}
                for item in valid[-self.history_turn_limit * 2:]
            )
        messages.append({"role": "user", "content": user_message})
        return messages

    def _payload(self, user_message, conversation_history, system_prompt, stream):
        payload = {
            "model": self._resolve_model_name(),
            "messages": self._messages(user_message, conversation_history, system_prompt),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "n_predict": self.max_tokens,
            "stream": stream,
            "cache_prompt": self.cache_prompt,
        }
        if self.disable_reasoning:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    @staticmethod
    def _normalize_endpoint_url(endpoint_url: str) -> str:
        trimmed = endpoint_url.rstrip("/")
        if trimmed.endswith("/v1/chat/completions"):
            return trimmed
        if trimmed.endswith("/v1"):
            return f"{trimmed}/chat/completions"
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
        resp = None
        try:
            resp = self._session.get(
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
        except (requests.exceptions.RequestException, ValueError) as exc:
            print(f"[LLM] Model discovery notice: {exc}")
        finally:
            if resp is not None:
                resp.close()

        self._resolved_model_name = requested
        return requested

    def generate_response(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        payload = self._payload(user_message, conversation_history, system_prompt, stream=False)
        start_time = time.monotonic()
        resp = None
        try:
            resp = self._session.post(
                self.endpoint_url,
                json=payload,
                timeout=(self.connect_timeout, self.timeout),
            )
            duration = time.monotonic() - start_time

            if resp.status_code == 200:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        item.get("text", "") for item in content if isinstance(item, dict)
                    )
                reply = content.strip() if isinstance(content, str) else ""

                timings = data.get("timings", {})
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", timings.get("prompt_n", "?"))
                output_tokens = usage.get("completion_tokens", timings.get("predicted_n", "?"))
                output_rate = timings.get("predicted_per_second")
                rate_text = f", {output_rate:.2f} tok/s" if isinstance(output_rate, (int, float)) else ""
                print(
                    f"[LLM] Gemma 4 completed in {duration:.2f}s "
                    f"(prompt={prompt_tokens}, output={output_tokens}{rate_text}, "
                    f"finish={choice.get('finish_reason', 'unknown')}): \"{reply}\""
                )

                if not reply:
                    reasoning = message.get("reasoning_content", "")
                    detail = " after producing hidden reasoning" if reasoning else ""
                    print(
                        f"[LLM] Empty visible response{detail}; using spoken recovery text. "
                        "Restart llama-server with --reasoning off --reasoning-budget 0 if this repeats."
                    )
                    return self.empty_response_text
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
        except (ValueError, TypeError, AttributeError) as exc:
            print(f"[LLM] Invalid response from llama-server: {exc}")
            return self.empty_response_text
        finally:
            if resp is not None:
                resp.close()

    def generate_response_stream(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ):
        """Yield text tokens in real time from llama-server SSE stream."""
        payload = self._payload(user_message, conversation_history, system_prompt, stream=True)
        start_time = time.monotonic()
        first_token_time = None
        accumulated_text = []

        resp = None
        try:
            resp = self._session.post(
                self.endpoint_url,
                json=payload,
                stream=True,
                timeout=(self.connect_timeout, self.timeout),
            )
            if resp.status_code != 200:
                print(f"[LLM] Server returned HTTP {resp.status_code}: {resp.text}")
                yield "By my troth, a mystical perturbation clouds my mind!"
                return

            # Requests' default 512-byte buffer can hold several tokens before
            # yielding a small SSE event, adding noticeable first-speech delay.
            for line in resp.iter_lines(chunk_size=1):
                if not line:
                    continue
                line_str = line.decode("utf-8") if isinstance(line, bytes) else str(line)
                if not line_str.startswith("data:"):
                    continue
                data_body = line_str[5:].strip()
                if data_body == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_body)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices", [])
                if choices:
                    token = choices[0].get("delta", {}).get("content", "")
                    if isinstance(token, str) and token:
                        if first_token_time is None:
                            first_token_time = time.monotonic() - start_time
                            print(f"[LLM] First token received in {first_token_time:.2f}s (TTFT)")
                        accumulated_text.append(token)
                        yield token

            total_duration = time.monotonic() - start_time
            full_reply = "".join(accumulated_text).strip()
            rate = len(accumulated_text) / max(0.001, total_duration)
            print(f"[LLM] Streaming finished in {total_duration:.2f}s ({rate:.2f} chunks/s): \"{full_reply}\"")
            if not full_reply:
                yield self.empty_response_text
        except requests.exceptions.RequestException as e:
            print(f"[LLM] Streaming connection error: {e}")
            # A mid-answer outage must not append an unrelated recovery sentence.
            if accumulated_text:
                raise
            yield "Hark! The castle magical currents are severed."
        finally:
            if resp is not None:
                resp.close()
