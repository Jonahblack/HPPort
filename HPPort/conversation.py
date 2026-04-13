import re
from pathlib import Path
from typing import List, Optional

import speech_recognition as sr

from audio import AudioPlayer

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - runtime dependency
    genai = None
    genai_types = None


class ConversationManager:
    def __init__(self, app_config):
        self.app_config = app_config
        self.config = app_config.raw["conversation"]
        self.audio_config = app_config.raw["audio"]
        self.audio_player = AudioPlayer(self.audio_config, credentials_path=app_config.google_credentials)
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.history: List[dict] = []
        self._genai_client = None

    def _get_microphone(self) -> sr.Microphone:
        if self.microphone is None:
            self.microphone = sr.Microphone(
                device_index=self.audio_config.get("mic_device_index"),
                sample_rate=int(self.audio_config.get("sample_rate", 16000)),
            )
        return self.microphone

    def prime_microphone(self) -> None:
        with self._get_microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)

    def detect_wake_word_once(self) -> bool:
        wake_word = self.app_config.wake_word.lower()
        timeout = float(self.config.get("wake_listen_timeout_seconds", 1.0))
        phrase_limit = float(self.config.get("wake_phrase_limit_seconds", 2.0))
        with self._get_microphone() as source:
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return False

        try:
            text = self.recognizer.recognize_sphinx(audio, keyword_entries=[(wake_word, 1.0)])
            return wake_word in text.lower()
        except sr.UnknownValueError:
            return False
        except Exception:
            try:
                text = self.recognizer.recognize_google(audio_data=audio, language=self.config["language"])
                return wake_word in text.lower()
            except Exception:
                return False

    def listen_once(self) -> Optional[str]:
        timeout = float(self.config.get("listen_timeout_seconds", 7.0))
        phrase_limit = float(self.config.get("phrase_time_limit_seconds", 7.0))
        use_cloud_stt = bool(self.audio_config.get("use_google_cloud_stt", False))

        credentials_json = None
        if use_cloud_stt and self.app_config.google_credentials:
            credentials_json = Path(self.app_config.google_credentials).read_text(encoding="utf-8")

        with self._get_microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return None

        try:
            if use_cloud_stt and credentials_json:
                text = self.recognizer.recognize_google_cloud(
                    audio_data=audio,
                    credentials_json=credentials_json,
                    language=self.config["language"],
                )
            else:
                text = self.recognizer.recognize_google(audio_data=audio, language=self.config["language"])
            return text.strip()
        except sr.UnknownValueError:
            return None
        except Exception:
            return None

    def is_stop_phrase(self, text: str) -> bool:
        return self.app_config.stop_phrase.lower() in text.lower()

    def greet_text(self, trigger_reason: str) -> str:
        if trigger_reason == "camera":
            return str(self.config.get("greeting_on_camera", "Hello there."))
        return str(self.config.get("greeting_on_voice", "Yes?"))

    def say(self, text: str, on_level=None) -> None:
        speech = self.audio_player.synthesize(text, language_code=self.config["language"])
        self.audio_player.speak(speech, on_level=on_level)

    def generate_reply(self, user_text: str) -> str:
        if genai is None or genai_types is None:
            raise RuntimeError("google-genai is not installed.")
        if not self.app_config.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        if self._genai_client is None:
            self._genai_client = genai.Client(api_key=self.app_config.gemini_api_key)

        trimmed_history = self.history[-int(self.config.get("max_history_messages", 8)) :]
        contents = list(trimmed_history)
        contents.append({"role": "user", "parts": [{"text": user_text}]})

        cfg = genai_types.GenerateContentConfig(
            temperature=0.9,
            system_instruction=self.config["system_prompt"],
            max_output_tokens=256,
        )
        response = self._genai_client.models.generate_content(
            model=self.config["gemini_model"],
            contents=contents,
            config=cfg,
        )
        reply_text = (getattr(response, "text", None) or "").strip()
        reply_text = re.sub(r"\s+", " ", reply_text)

        self.history.append({"role": "user", "parts": [{"text": user_text}]})
        if reply_text:
            self.history.append({"role": "model", "parts": [{"text": reply_text}]})
        self.history = self.history[-int(self.config.get("max_history_messages", 8)) :]
        return reply_text

    def reset_history(self) -> None:
        self.history = []

    def close(self) -> None:
        self.audio_player.close()
