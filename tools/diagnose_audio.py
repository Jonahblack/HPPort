#!/usr/bin/env python3
"""Print microphone, speaker, and Piper diagnostics for Raspberry Pi troubleshooting."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from contextlib import contextmanager
from typing import Any, Dict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from config import load_config
from tts.piper import PiperTTS


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


@contextmanager
def time_limit(seconds: int, label: str):
    def _handler(_signum, _frame):
        raise TimeoutError(f"{label} timed out after {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def run_command(label: str, cmd: list[str], timeout_seconds: int = 4) -> None:
    print_section(label)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
        if not stdout and not stderr:
            print(f"{label} returned no output.")
    except FileNotFoundError:
        print(f"{cmd[0]} not installed.")
    except subprocess.TimeoutExpired:
        print(f"{label} timed out after {timeout_seconds}s.")


def diagnose_speech_recognition() -> None:
    print_section("SpeechRecognition")
    try:
        import speech_recognition as sr  # type: ignore

        with time_limit(4, "SpeechRecognition probe"):
            names = sr.Microphone.list_microphone_names()
        if not names:
            print("No microphone devices reported.")
            return

        for index, name in enumerate(names):
            print(f"[{index}] {name}")
    except TimeoutError as exc:
        print(str(exc))
    except Exception as exc:
        print(f"SpeechRecognition unavailable: {exc}")


def diagnose_sounddevice() -> None:
    print_section("sounddevice")
    try:
        import sounddevice as sd  # type: ignore

        with time_limit(4, "sounddevice probe"):
            print(f"default.device = {sd.default.device}")
            devices = sd.query_devices()
        for index, device in enumerate(devices):
            print(
                f"[{index}] {device['name']} | "
                f"in={device['max_input_channels']} out={device['max_output_channels']} "
                f"default_sr={device['default_samplerate']}"
            )
    except TimeoutError as exc:
        print(str(exc))
    except Exception as exc:
        print(f"sounddevice unavailable: {exc}")


def diagnose_pyaudio() -> None:
    print_section("PyAudio")
    try:
        import pyaudio  # type: ignore

        with time_limit(4, "PyAudio probe"):
            pa = pyaudio.PyAudio()
            try:
                default_in = pa.get_default_input_device_info()
            except Exception:
                default_in = None
            try:
                default_out = pa.get_default_output_device_info()
            except Exception:
                default_out = None

            print(f"default_input = {default_in}")
            print(f"default_output = {default_out}")
            print(f"device_count = {pa.get_device_count()}")
            for index in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(index)
                print(
                    f"[{index}] {info.get('name')} | "
                    f"in={info.get('maxInputChannels')} out={info.get('maxOutputChannels')} "
                    f"default_sr={info.get('defaultSampleRate')}"
                )
    except TimeoutError as exc:
        print(str(exc))
    except Exception as exc:
        print(f"PyAudio unavailable: {exc}")


def diagnose_piper(config: Dict[str, Any]) -> None:
    print_section("Piper")
    tts = PiperTTS(config)
    print(f"configured_path = {config['tts'].get('piper_binary_path')}")
    print(f"selected_path = {tts.piper_binary}")
    print(f"is_file = {os.path.isfile(tts.piper_binary)}")
    print(f"is_dir = {os.path.isdir(tts.piper_binary)}")
    print(f"model_path = {tts.model_path}")
    print(f"model_exists = {os.path.exists(tts.model_path)}")


def main() -> None:
    config = load_config("portrait_config.json")
    print_section("Config")
    print(json.dumps({"stt": config.get("stt", {}), "tts": config.get("tts", {}), "llm": config.get("llm", {})}, indent=2))
    run_command("arecord -l", ["arecord", "-l"])
    run_command("aplay -l", ["aplay", "-l"])
    diagnose_speech_recognition()
    diagnose_sounddevice()
    diagnose_pyaudio()
    diagnose_piper(config)


if __name__ == "__main__":
    main()
