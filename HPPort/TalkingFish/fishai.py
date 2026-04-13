#!/usr/bin/env python3
"""
TalkingFish: wake-word–activated conversational fish ("Wilhelm")
that chats using Gemini and speaks via Google Cloud Text-to-Speech.
Designed to run on a Raspberry Pi 3 with minimal dependencies.

Wake word:  "wilhelm"
Stop phrase: "goodbye wilhelm"

Flow
----
1) Idle: continuously listen locally for the wake word using PocketSphinx.
2) On wake: greet and enter a conversation loop.
3) Conversation: capture a user utterance, send to Gemini, speak the reply.
4) Exit conversation loop on the phrase "goodbye wilhelm", then return to idle.

Env vars you must set
---------------------
- GEMINI_API_KEY: Gemini (Google AI Studio) API key.
- GOOGLE_APPLICATION_CREDENTIALS: path to a GCP service-account JSON with
  permission for Text-to-Speech (and optionally Speech-to-Text if you later
  decide to switch to Cloud STT).
- Optional:
  - MIC_DEVICE_INDEX: override microphone device index (integer).
  - TALKINGFISH_LANG: BCP-47 language (default: en-US).

Install (on Raspberry Pi OS)
----------------------------
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev libasound2-dev portaudio19-dev
pip3 install -r requirements.txt

Run
---
python3 fishai.py
"""

import os
import re
import sys
import time
import json
import queue
import signal
import tempfile
import threading
from pathlib import Path
from typing import Optional, List

import speech_recognition as sr
import pygame

# Google libraries
from google import genai
from google.genai import types as genai_types
from google.cloud import texttospeech as tts

# ----------------------------- Configuration ----------------------------- #

LANG = os.getenv("TALKINGFISH_LANG", "en-US")
WAKE_WORD = "wilhelm"
STOP_PHRASE = "goodbye wilhelm"

# Audio / mic
MIC_DEVICE_INDEX = None
try:
    if os.getenv("MIC_DEVICE_INDEX") is not None:
        MIC_DEVICE_INDEX = int(os.getenv("MIC_DEVICE_INDEX"))
except Exception:
    MIC_DEVICE_INDEX = None

MIC_SAMPLE_RATE = 16000       # lower sample rate is easier on Pi 3
MIC_CHUNK_SIZE = 1024

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Voice
VOICE_SPEAKING_RATE = float(os.getenv("TTS_SPEAKING_RATE", "0.98"))  # slightly slower
VOICE_PITCH = float(os.getenv("TTS_PITCH", "0.0"))

SYSTEM_PROMPT = (
    "You are Wilhelm, a witty but kind conversational fish. "
    "Keep replies concise (1-3 sentences) and speak in a friendly tone. "
    "If the user says 'goodbye wilhelm', say a short goodbye."
)

# ----------------------------- Helpers ----------------------------- #

def fatal(msg: str) -> None:
    print(f"[FATAL] {msg}", file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)


def info(msg: str) -> None:
    print(f"[TalkingFish] {msg}", flush=True)


def init_pygame_audio() -> None:
    # conservative mixer settings for the Pi 3
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)
    except Exception as e:
        fatal(f"Failed to init audio: {e}")


def play_audio_bytes(audio_bytes: bytes) -> None:
    """
    Play MP3 bytes using pygame with a temporary file. Serialize playback.
    """
    # Stop any existing playback
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            # Some pygame versions need unload to switch files cleanly
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
    except Exception:
        pass

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()
        pygame.mixer.music.load(tmp.name)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)  # keep the main thread responsive
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def split_into_tts_chunks(text: str) -> List[str]:
    """
    Split text into sentence-like chunks to reduce latency and memory.
    """
    text = text.strip()
    if not text:
        return []
    # Try hard sentence splits, then fall back to sized chunks
    parts = re.split(r'(?<=[.!?])\s+', text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= 220:
            out.append(p)
        else:
            # soft wrap long sentences
            while len(p) > 0:
                out.append(p[:200])
                p = p[200:]
    return out


# ----------------------------- STT ----------------------------- #

_recognizer = sr.Recognizer()
_microphone = None  # created lazily to avoid failing when no mic yet


def get_microphone() -> sr.Microphone:
    global _microphone
    if _microphone is None:
        _microphone = sr.Microphone(device_index=MIC_DEVICE_INDEX, sample_rate=MIC_SAMPLE_RATE)
    return _microphone


def listen_once(timeout: float = 5.0, phrase_time_limit: float = 6.0) -> Optional[str]:
    """
    Capture one utterance and transcribe with SpeechRecognition's Google Web Speech
    (no key) as a pragmatic default. It's light and works fine on Pi 3.
    If you prefer Google Cloud STT, set USE_GOOGLE_CLOUD_STT=1 and provide credentials.
    """
    USE_GC = os.getenv("USE_GOOGLE_CLOUD_STT", "").lower() in ("1", "true", "yes")
    creds_json = None
    if USE_GC:
        key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        if not key_path or not Path(key_path).exists():
            info("USE_GOOGLE_CLOUD_STT=1 but GOOGLE_APPLICATION_CREDENTIALS is missing; falling back to Google Web Speech.")
            USE_GC = False
        else:
            try:
                creds_json = Path(key_path).read_text()
            except Exception as e:
                info(f"Could not read credentials JSON: {e}. Falling back to Google Web Speech.")
                USE_GC = False

    with get_microphone() as source:
        # Light normalization, helps on noisy rooms
        _recognizer.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return None

    try:
        if USE_GC and creds_json:
            text = _recognizer.recognize_google_cloud(
                audio_data=audio,
                credentials_json=creds_json,
                language=LANG,
            )
        else:
            text = _recognizer.recognize_google(audio_data=audio, language=LANG)
        return text.strip()
    except sr.UnknownValueError:
        return None
    except Exception as e:
        info(f"STT error: {e}")
        return None


def detect_wake_word(timeout: float = 1.2, phrase_time_limit: float = 2.2) -> bool:
    """
    Use PocketSphinx via SpeechRecognition to do keyword spotting locally.
    """
    with get_microphone() as source:
        try:
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return False
    try:
        # Keyword spotting: tune sensitivity if needed (lower = less sensitive)
        text = _recognizer.recognize_sphinx(audio, keyword_entries=[(WAKE_WORD, 1.0)])
        return WAKE_WORD in text.lower()
    except sr.UnknownValueError:
        return False
    except Exception:
        # If pocketsphinx isn't available, last-resort: quick web STT check for the word
        try:
            txt = _recognizer.recognize_google(audio_data=audio, language=LANG)
            return WAKE_WORD in txt.lower()
        except Exception:
            return False


# ----------------------------- TTS ----------------------------- #

_tts_client = None
def get_tts_client() -> tts.TextToSpeechClient:
    global _tts_client
    if _tts_client is None:
        # Will use GOOGLE_APPLICATION_CREDENTIALS if set
        _tts_client = tts.TextToSpeechClient()
    return _tts_client


def tts_say(text: str) -> None:
    """
    Synthesize in small chunks to reduce latency, play sequentially.
    """
    client = get_tts_client()
    for chunk in split_into_tts_chunks(text):
        synthesis_input = tts.SynthesisInput(text=chunk)
        voice = tts.VoiceSelectionParams(language_code=LANG)
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.MP3,
            speaking_rate=VOICE_SPEAKING_RATE,
            pitch=VOICE_PITCH,
        )
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        play_audio_bytes(response.audio_content)


# ----------------------------- Gemini ----------------------------- #

_genai_client = None
def get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        if not GEMINI_API_KEY:
            fatal("GEMINI_API_KEY is not set.")
        # v1alpha streams are fine; keep defaults light.
        _genai_client = genai.Client(api_key=GEMINI_API_KEY)
    return _genai_client


def gemini_reply(history: List[dict], user_text: str, stream: bool = True) -> str:
    """
    Ask Gemini for a reply. For the Pi 3, we keep it simple:
    - Use streaming to start talking sooner, but buffer until sentence ends.
    Returns the full text that was spoken.
    """
    client = get_genai_client()

    contents = []
    # Add a brief system instruction up front
    cfg = genai_types.GenerateContentConfig(
        temperature=0.9,
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=256,
    )

    # Keep a short rolling history to limit tokens
    trimmed_history = history[-6:]
    contents.extend(trimmed_history)
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    full_text = ""

    if stream:
        buffer = ""
        try:
            stream_iter = client.models.generate_content_stream(
                model=MODEL_NAME,
                contents=contents,
                config=cfg,
            )
            for chunk in stream_iter:
                piece = getattr(chunk, "text", None)
                if not piece:
                    continue
                full_text += piece
                buffer += piece

                # If we reached a sentence end or buffer is long, speak it
                if re.search(r"[.!?]\s$", buffer) or len(buffer) > 180:
                    speak = buffer.strip()
                    buffer = ""
                    if speak:
                        tts_say(speak)
            # speak whatever is left
            tail = buffer.strip()
            if tail:
                tts_say(tail)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            info(f"Gemini streaming failed ({e}); falling back to non-streaming.")
            stream = False

    if not stream:
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=cfg,
            )
            text = getattr(resp, "text", None) or ""
            full_text = text
            if text:
                tts_say(text)
        except Exception as e:
            info(f"Gemini request failed: {e}")
            full_text = ""

    return full_text


# ----------------------------- Main loop ----------------------------- #

def main() -> None:
    # Ctrl+C friendly
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    info("Initializing audio...")
    init_pygame_audio()

    # Ensure mic works
    try:
        with get_microphone() as s:
            _recognizer.adjust_for_ambient_noise(s, duration=0.2)
    except Exception as e:
        fatal(f"No microphone? {e}")

    info("TalkingFish is ready. Say 'wilhelm' to start a chat.")

    # Friendly startup line
    tts_say("Hello. Say Wilhelm to talk to me.")

    history: List[dict] = []

    while True:
        # 1) Idle, wait for wake word (short non-blocking listens)
        if not detect_wake_word(timeout=1.0, phrase_time_limit=2.0):
            continue

        info("Wake word detected!")
        tts_say("Hey there! I'm Wilhelm. What's up?")

        # 2) Conversation loop
        while True:
            user_text = listen_once(timeout=7.0, phrase_time_limit=7.0)
            if not user_text:
                # a brief nudge; don't spam
                info("Didn't catch that.")
                tts_say("Sorry, I didn't catch that. Could you repeat?")
                continue

            low = user_text.lower().strip()
            if STOP_PHRASE in low:
                tts_say("Goodbye! Call me again by saying Wilhelm.")
                info("Stop phrase heard; returning to idle.")
                # clear history occasionally so we don't bloat tokens
                history = history[-4:]
                break

            info(f"User: {user_text}")
            history.append({"role": "user", "parts": [{"text": user_text}]})

            reply = gemini_reply(history, user_text, stream=True)
            if reply:
                history.append({"role": "model", "parts": [{"text": reply}]})

            # Keep only the last N messages to constrain context size
            if len(history) > 8:
                history = history[-8:]


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            pygame.mixer.quit()
        except Exception:
            pass
