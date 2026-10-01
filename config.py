"""Configuration loader and schema definition for Talking Portrait."""

import json
import os
import argparse
from copy import deepcopy
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "hardware": {
        "target": "raspberry_pi_5",
        "storage_mount_path": "/mnt/portrait",
        "models_dir": "/mnt/portrait/models",
        "cache_dir": "/mnt/portrait/cache",
        "audio_dir": "/mnt/portrait/audio",
        "logs_dir": "/mnt/portrait/logs",
    },
    "conversation_mode": "auto",  # Prefer Gemini text + Piper; fall back to the local model.
    "gemini_live": {
        "enabled": True,
        "model": "gemini-3.1-flash-live-preview",
        "voice_name": "Charon",
        "response_voice": "piper",  # Same voice for cloud, local replies, and greeting.
        "text_model": "gemini-3.5-flash-lite",
        "max_output_tokens": 128,
        "timeout_seconds": 12.0,
        "turn_timeout_seconds": 30.0,
        "retry_cooldown_seconds": 30.0,
        "api_key_env": "GEMINI_API_KEY",
        "max_daily_tokens": 250000,
        "max_session_tokens": 40000,
        "storage_file": "token_usage.json",
        "quota_fallback_text": "My celestial communications are depleted for today! I shall converse with thee through local enchantments instead.",
    },
    "state_machine": {
        "wake_confirm_frames": 3,
        "wake_confirm_timeout_seconds": 1.5,
        "silence_timeout_seconds": 4.0,
        "max_listen_duration_seconds": 10.0,
        "max_consecutive_silence": 2,
        "cooldown_duration_seconds": 8.0,
    },
    "vision": {
        "driver": "hailo",
        "confidence_threshold": 0.55,
        "poll_interval_seconds": 0.1,
        "camera_backend": "auto",
        "camera_device_index": 0,
        "camera_width": 640,
        "camera_height": 480,
        "camera_fps": 15,
        "analysis_width": 320,
    },
    "llm": {
        "driver": "llama_client",
        "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions",
        "model_name": "gemma-4-e2b-instruction",
        "temperature": 0.35,
        "max_tokens": 48,
        "timeout_seconds": 90.0,
        "connect_timeout_seconds": 5.0,
        "history_turn_limit": 2,
        "cache_prompt": True,
        "disable_reasoning": True,
        "empty_response_text": "The castle spirits stole my answer. Ask once more, brave visitor!",
        "system_prompt": (
            "You are Wilhelm, a bold eccentric forest guardian and noble warrior in an enchanted portrait. "
            "Answer in one lively spoken sentence under 20 words."
        ),
        "greeting_prompt": "Ah, a visitor arrives before my frame! State your business, noble wanderer!",
    },
    "stt": {
        "driver": "local_stt",
        "engine": "faster_whisper",
        "model_size": "tiny.en",
        "language": "en",
        "device": "cpu",
        "compute_type": "int8",
        "vad_filter": True,
        "energy_threshold": 300,
        "dynamic_energy_threshold": True,
        "ambient_calibration_seconds": 0.3,
        "pause_threshold": 0.5,
        "non_speaking_duration": 0.2,
        "phrase_threshold": 0.15,
        "cpu_threads": 2,
        "allow_online_fallback": False,
        "local_files_only": False,
        "microphone_device_index": None,
        "microphone_name": "",
        "sample_rate": None,
        "chunk_size": 1024,
        "arecord_device": "",
    },
    "tts": {
        "driver": "piper",
        "runtime": "auto",
        "warmup_enabled": True,
        "synthesis_timeout_seconds": 30.0,
        "cache_max_entries": 128,
        "allow_synthetic_fallback": False,
        "piper_binary_path": "/mnt/portrait/models/piper/piper",
        "model_path": "/mnt/portrait/models/piper/en_US-ryan-medium.onnx",
        "model_config_path": "/mnt/portrait/models/piper/en_US-ryan-medium.onnx.json",
        "speaker_id": 0,
        "length_scale": 1.0,
        "noise_scale": 0.667,
        "noise_w": 0.8,
        "cache_enabled": True,
        "cache_dir": "/mnt/portrait/cache/tts",
        "audio_driver": "auto",
        "playback_sample_rate": 22050,
        "playback_channels": 1,
        "playback_buffer_size": 512,
    },
    "renderer": {
        "window_title": "Harry Potter Talking Portrait (Gemma 4)",
        "width": 1024,
        "height": 768,
        "fullscreen": False,
        "fps": 30,
        "show_debug_hud": False,
        "show_camera_pip": False,
        "assets_dir": "assets",
        "asset_mode": "full_frames",
        "sprite_files": {
            "base": "forest_warrior_neutral.png",
            "eyes_closed": "forest_warrior_blink.png",
            "mouth_1": "forest_warrior_neutral.png",
            "mouth_2": "forest_warrior_mouth_2.png",
            "mouth_3": "forest_warrior_mouth_3.png",
        },
        "camera_motion": True,
        "ambient_motes": True,
        "blink_min_seconds": 2.2,
        "blink_max_seconds": 5.5,
        "blink_duration_ms": 180,
        "amplitude_threshold_mouth_2": 0.15,
        "amplitude_threshold_mouth_3": 0.45,
    },
    "logging": {
        "log_level": "INFO",
        "latency_profiling": True,
        "log_to_file": True,
    },
}


def load_config(config_path: str = "portrait_config.json", demo_mode: bool = False) -> Dict[str, Any]:
    """Load configuration from JSON file with fallback defaults and demo mode overrides."""
    config = deepcopy(DEFAULT_CONFIG)

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                _merge_config(config, user_cfg)
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid configuration {config_path}: {exc}") from exc
    else:
        print(f"[Config] File {config_path} not found. Using default in-memory config.")

    if demo_mode:
        config["vision"]["driver"] = "mock"
        config["llm"]["driver"] = "mock"
        config["tts"]["driver"] = "mock"
        config["stt"]["driver"] = "keyboard"
        config["renderer"]["fullscreen"] = False
        config["gemini_live"]["enabled"] = False
        # Demo runs should never depend on an SSD mount or write to system paths.
        config["hardware"]["audio_dir"] = None
        config["hardware"]["cache_dir"] = os.path.join(os.path.dirname(os.path.abspath(config_path)), ".cache")

    if config["conversation_mode"] not in ("auto", "local", "gemini_live"):
        raise ValueError("conversation_mode must be auto, local, or gemini_live")
    if config["gemini_live"]["response_voice"] not in ("piper", "native"):
        raise ValueError("gemini_live.response_voice must be piper or native")
    for section, keys in {
        "renderer": ("fps", "width", "height"),
        "state_machine": ("silence_timeout_seconds", "max_listen_duration_seconds"),
        "vision": ("poll_interval_seconds",),
    }.items():
        for key in keys:
            value = config[section][key]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or value <= 0:
                raise ValueError(f"{section}.{key} must be a positive number")

    return config


def _merge_config(target, source):
    if not isinstance(source, dict):
        raise ValueError("Expected a JSON object")
    for key, value in source.items():
        if isinstance(target.get(key), dict):
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            _merge_config(target[key], value)
        else:
            target[key] = deepcopy(value)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Talking Portrait - Gemma 4 on Raspberry Pi 5")
    parser.add_argument(
        "--config",
        type=str,
        default="portrait_config.json",
        help="Path to JSON configuration file",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in desktop simulation/demo mode using mock drivers",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Force fullscreen rendering on HDMI display",
    )
    return parser.parse_args()
