import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class AppConfig:
    raw: Dict[str, Any]
    root_dir: Path
    config_path: Path
    gemini_api_key: str = ""
    google_credentials: str = ""

    @property
    def demo_mode(self) -> bool:
        return bool(self.raw.get("demo_mode", {}).get("enabled", False))

    @property
    def wake_word(self) -> str:
        return str(self.raw.get("conversation", {}).get("wake_word", "portrait")).strip()

    @property
    def stop_phrase(self) -> str:
        return str(self.raw.get("conversation", {}).get("stop_phrase", "goodbye portrait")).strip()

    @property
    def camera_enabled(self) -> bool:
        return bool(self.raw.get("camera", {}).get("enabled", True))

    @property
    def cooldown_seconds(self) -> float:
        return float(self.raw.get("cooldown", {}).get("seconds", 12.0))

    @property
    def max_silence_turns(self) -> int:
        return int(self.raw.get("conversation", {}).get("max_silence_turns", 2))


DEFAULT_CONFIG: Dict[str, Any] = {
    "demo_mode": {
        "enabled": False,
        "auto_wake_on_start": True,
        "auto_wake_interval_seconds": 0,
    },
    "renderer": {
        "width": 800,
        "height": 480,
        "fps": 30,
        "window_title": "Talking Portrait",
        "background_color": [18, 21, 28],
        "accent_color": [198, 134, 73],
        "eye_color": [248, 244, 236],
        "pupil_color": [32, 28, 27],
        "mouth_color": [126, 48, 43],
        "status_text_color": [232, 228, 220],
        "headless": False,
    },
    "camera": {
        "enabled": True,
        "backend": "picam2",
        "index": 0,
        "width": 1280,
        "height": 720,
        "fps": 20,
        "hef_path": "models/yolov5m.hef",
        "hailo_threshold": 0.55,
        "poll_interval_seconds": 0.12,
        "cooldown_seconds": 15.0,
        "motion_fallback_enabled": True,
        "voice_only_fallback": True,
    },
    "conversation": {
        "language": "en-US",
        "wake_word": "portrait",
        "stop_phrase": "goodbye portrait",
        "gemini_model": "gemini-2.0-flash",
        "system_prompt": (
            "You are a haunted talking portrait mounted on a wall. "
            "You are warm, playful, and a little uncanny. "
            "Keep replies concise, natural, and suitable for speech. "
            "Prefer one to three sentences."
        ),
        "listen_timeout_seconds": 7.0,
        "phrase_time_limit_seconds": 7.0,
        "wake_listen_timeout_seconds": 1.0,
        "wake_phrase_limit_seconds": 2.0,
        "max_history_messages": 8,
        "max_silence_turns": 2,
        "greeting_on_camera": "Hello there. I saw you walk up. What would you like to talk about?",
        "greeting_on_voice": "Yes? I am listening.",
        "silence_prompt": "I didn't quite catch that. Please try again.",
        "farewell": "Very well. Until next time.",
    },
    "audio": {
        "sample_rate": 16000,
        "tts_speaking_rate": 0.98,
        "tts_pitch": 0.0,
        "tts_voice_name": "",
        "tts_volume": 1.0,
        "use_google_cloud_stt": False,
        "mic_device_index": None,
    },
    "cooldown": {
        "seconds": 10.0,
    },
}


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(config)
    updated["conversation"] = dict(updated.get("conversation", {}))
    updated["audio"] = dict(updated.get("audio", {}))
    updated["demo_mode"] = dict(updated.get("demo_mode", {}))

    if os.getenv("PORTRAIT_WAKE_WORD"):
        updated["conversation"]["wake_word"] = os.environ["PORTRAIT_WAKE_WORD"]
    if os.getenv("PORTRAIT_STOP_PHRASE"):
        updated["conversation"]["stop_phrase"] = os.environ["PORTRAIT_STOP_PHRASE"]
    if os.getenv("GEMINI_MODEL"):
        updated["conversation"]["gemini_model"] = os.environ["GEMINI_MODEL"]
    if os.getenv("TALKINGPORTRAIT_LANG"):
        updated["conversation"]["language"] = os.environ["TALKINGPORTRAIT_LANG"]
    if os.getenv("MIC_DEVICE_INDEX"):
        try:
            updated["audio"]["mic_device_index"] = int(os.environ["MIC_DEVICE_INDEX"])
        except ValueError:
            pass
    if os.getenv("USE_GOOGLE_CLOUD_STT"):
        updated["audio"]["use_google_cloud_stt"] = os.environ["USE_GOOGLE_CLOUD_STT"].lower() in {"1", "true", "yes"}
    if os.getenv("PORTRAIT_DEMO_MODE"):
        updated["demo_mode"]["enabled"] = os.environ["PORTRAIT_DEMO_MODE"].lower() in {"1", "true", "yes"}
    return updated


def load_config(config_path: Optional[str] = None) -> AppConfig:
    root_dir = Path(__file__).resolve().parent
    chosen_path = Path(config_path) if config_path else root_dir / "portrait_config.json"

    config_data = dict(DEFAULT_CONFIG)
    if chosen_path.exists():
        user_config = json.loads(chosen_path.read_text(encoding="utf-8"))
        config_data = _deep_merge(config_data, user_config)

    config_data = _apply_env_overrides(config_data)
    return AppConfig(
        raw=config_data,
        root_dir=root_dir,
        config_path=chosen_path,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip(),
    )
