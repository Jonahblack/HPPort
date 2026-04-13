# Talking Portrait for Raspberry Pi 5

This repo now includes a first-pass talking portrait app that combines:

- HauntPi-style camera access and person-trigger logic.
- TalkingFish-style wake word, Gemini chat, and Google Cloud TTS.
- A finite state portrait loop with idle animation, blinking, eye drift, and mouth motion during speech.

## Files

- `main.py`
- `config.py`
- `state_machine.py`
- `camera_trigger.py`
- `conversation.py`
- `audio.py`
- `renderer.py`
- `portrait_config.json`
- `assets/`
- `docs/`

## Hardware

- Raspberry Pi 5
- Raspberry Pi Camera Module
- Hailo AI HAT or HAT+
- USB microphone
- Speaker
- Optional HDMI display for local preview

## Install

1. Install system packages:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev libasound2-dev portaudio19-dev python3-pygame
```

2. Install Python packages:

```bash
pip3 install -r requirements.txt
```

3. Set environment variables:

```bash
export GEMINI_API_KEY="your_google_ai_studio_key"
export GOOGLE_APPLICATION_CREDENTIALS="/home/pi/keys/tts-service-account.json"
```

4. Put your Hailo `.hef` at `models/yolov5m.hef` or change `portrait_config.json`.

## Run

Standard mode:

```bash
python3 main.py
```

Demo mode:

```bash
python3 main.py --demo
```

Wake sources:

- Camera detection when available.
- Wake word detection.
- Demo wake via `Space` in the portrait window.

Default stop phrase: `goodbye portrait`

## State Machine

- `IDLE`
- `WAKE_PENDING`
- `LISTENING`
- `THINKING`
- `SPEAKING`
- `COOLDOWN`

## Fallbacks

- Hailo unavailable: falls back to motion-based camera triggering.
- Camera unavailable: still works in wake-word mode.
- `--demo`: disables camera and lets you test animation plus speech first.

## Still Needs Hardware Tuning

- Hailo threshold and model choice.
- Camera framing and cooldown for your installation.
- Mic gain and wake-word sensitivity.
- Speaker volume to avoid self-triggering.
- Final renderer sizing for your display.
