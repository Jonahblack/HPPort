"""
Configuration management for the Talking Portrait system.
Loads settings from portrait_config.json and provides strongly-typed configurations.
"""

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class HardwareConfig:
    target: str = "raspberry_pi_5"
    storage_mount_path: str = "/mnt/portrait"
    models_dir: str = "/mnt/portrait/models"
    cache_dir: str = "/mnt/portrait/cache"
    audio_dir: str = "/mnt/portrait/audio"
    logs_dir: str = "/mnt/portrait/logs"


@dataclass
class StateMachineConfig:
    wake_confirm_frames: int = 3
    wake_confirm_timeout_seconds: float = 1.5
    silence_timeout_seconds: float = 2.0
    max_listen_duration_seconds: float = 10.0
    max_consecutive_silence: int = 2
    cooldown_duration_seconds: float = 8.0


@dataclass
class VisionConfig:
    driver: str = "hailo"  # 'hailo' or 'mock'
    confidence_threshold: float = 0.55
    poll_interval_seconds: float = 0.1
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30


@dataclass
class LLMConfig:
    driver: str = "llama_client"  # 'llama_client' or 'mock_client'
    endpoint_url: str = "http://127.0.0.1:8080/v1/chat/completions"
    model_name: str = "gemma-4-e2b-instruct"
    temperature: float = 0.7
    max_tokens: int = 150
    system_prompt: str = (
        "You are Lord Cadogan, an eccentric and chivalrous knight trapped inside an enchanted "
        "Harry Potter-style portrait. Keep your answers brief, lively, and in-character (1 to 3 short sentences). "
        "Never use emoji. Greet visitors with flair and ask engaging questions."
    )
    greeting_prompt: str = "Ah, a visitor arrives before my frame! State your business, noble wanderer!"


@dataclass
class STTConfig:
    driver: str = "local_stt"  # 'local_stt' or 'keyboard_stt'
    engine: str = "faster_whisper"
    model_size: str = "tiny.en"
    language: str = "en"
    device: str = "cpu"
    compute_type: str = "int8"
    vad_filter: bool = True
    energy_threshold: int = 300


@dataclass
class TTSConfig:
    driver: str = "piper"  # 'piper' or 'mock_tts'
    piper_binary_path: str = "/mnt/portrait/models/piper/piper"
    model_path: str = "/mnt/portrait/models/piper/en_US-ryan-high.onnx"
    model_config_path: str = "/mnt/portrait/models/piper/en_US-ryan-high.onnx.json"
    speaker_id: int = 0
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w: float = 0.8


@dataclass
class RendererConfig:
    window_title: str = "Harry Potter Talking Portrait (Gemma 4)"
    width: int = 1024
    height: int = 768
    fullscreen: bool = false
    fps: int = 60
    assets_dir: str = "assets"
    blink_min_seconds: float = 2.0
    blink_max_seconds: float = 5.0
    blink_duration_ms: int = 150
    amplitude_threshold_mouth_2: float = 0.15
    amplitude_threshold_mouth_3: float = 0.45


@dataclass
class LoggingConfig:
    log_level: str = "INFO"
    latency_profiling: bool = True
    log_to_file: bool = True


@dataclass
class AppConfig:
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    state_machine: StateMachineConfig = field(default_factory=StateMachineConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    renderer: RendererConfig = field(default_factory=RendererConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(config_path: str = "portrait_config.json", demo_mode: bool = False) -> AppConfig:
    """Load configuration from JSON file with optional demo overrides."""
    config = AppConfig()
    path = Path(config_path)

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)

            if "hardware" in data:
                config.hardware = HardwareConfig(**data["hardware"])
            if "state_machine" in data:
                config.state_machine = StateMachineConfig(**data["state_machine"])
            if "vision" in data:
                config.vision = VisionConfig(**data["vision"])
            if "llm" in data:
                config.llm = LLMConfig(**data["llm"])
            if "stt" in data:
                config.stt = STTConfig(**data["stt"])
            if "tts" in data:
                config.tts = TTSConfig(**data["tts"])
            if "renderer" in data:
                config.renderer = RendererConfig(**data["renderer"])
            if "logging" in data:
                config.logging = LoggingConfig(**data["logging"])

            logger.info("Loaded configuration from %s", config_path)
        except Exception as e:
            logger.warning("Failed to parse %s: %s. Using default configuration.", config_path, e)
    else:
        logger.info("Configuration file %s not found. Using defaults.", config_path)

    if demo_mode:
        logger.info("Enabling Desktop Demo Mode overrides.")
        config.vision.driver = "mock"
        config.stt.driver = "keyboard_stt"
        config.tts.driver = "mock_tts"
        config.llm.driver = "mock_client"
        config.renderer.fullscreen = False

    return config
