"""Configuration loader and schema definition for Talking Portrait."""

import json
import os
import argparse
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
    "state_machine": {
        "wake_confirm_frames": 3,
        "wake_confirm_timeout_seconds": 1.5,
        "silence_timeout_seconds": 2.0,
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
        "camera_fps": 30,
    },
    "llm": {
        "driver": "llama_client",
        "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions",
        "model_name": "gemma-4-e2b-instruction",
        "temperature": 0.35,
        "max_tokens": 24,
        "timeout_seconds": 90.0,
        "connect_timeout_seconds": 5.0,
        "history_turn_limit": 1,
        "cache_prompt": True,
        "disable_reasoning": True,
        "empty_response_text": "The castle spirits stole my answer. Ask once more, brave visitor!",
        "system_prompt": (
            "You are Lord Cadogan, a bold eccentric knight in an enchanted portrait. "
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
        "microphone_device_index": None,
        "microphone_name": "",
        "sample_rate": None,
        "chunk_size": 1024,
        "arecord_device": "",
    },
    "tts": {
        "driver": "piper",
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
        "fps": 60,
        "assets_dir": "assets",
        "blink_min_seconds": 2.0,
        "blink_max_seconds": 5.0,
        "blink_duration_ms": 150,
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
    config = dict(DEFAULT_CONFIG)

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                for section, values in user_cfg.items():
                    if isinstance(values, dict) and section in config:
                        config[section].update(values)
                    else:
                        config[section] = values
        except Exception as e:
            print(f"[Config] Warning: Failed to parse {config_path} ({e}). Using default settings.")
    else:
        print(f"[Config] File {config_path} not found. Using default in-memory config.")

    if demo_mode:
        config["vision"]["driver"] = "mock"
        config["llm"]["driver"] = "mock"
        config["tts"]["driver"] = "mock"
        config["stt"]["driver"] = "keyboard"
        config["renderer"]["fullscreen"] = False

    return config


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
