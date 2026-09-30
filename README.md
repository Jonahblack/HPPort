# Talking Portrait

An animated, speaking portrait built primarily for **Raspberry Pi 5**. The native Python application combines camera motion triggers, local Whisper transcription, Gemini or a local llama.cpp model, and Piper speech. The React application is a separate browser demo and dashboard.

## Raspberry Pi quick start

Use 64-bit Raspberry Pi OS, a USB microphone, speakers, and a display. An SSD is recommended for models. Follow [the Pi setup guide](docs/setup_pi.md) for model downloads, audio configuration, and startup.

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev python3-pyaudio \
  python3-picamera2 libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 \
  libsdl2-ttf-2.0-0 alsa-utils ffmpeg
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-piper.txt
python main.py --fullscreen
```

Configure model paths in `portrait_config.json` before starting. Piper needs the Ryan medium `.onnx` voice and its `.onnx.json` configuration. The optional Python Piper runtime keeps the voice loaded; the standalone Piper executable also works.

For a hardware-free preview:

```bash
python main.py --demo
```

Demo mode uses scripted replies and synthetic tones, so it is useful for checking animation and state transitions, not voice quality.

## Conversation and voice

The default `conversation_mode: "auto"` uses Gemini text generation when a key and token budget are available, and falls back to the local llama.cpp server. Both routes, including the greeting, use **the same Piper Ryan voice**. This keeps the voice consistent when the model changes.

```bash
cp .env.example .env
# Set GEMINI_API_KEY in .env for optional cloud responses.
```

| Setting | Behavior |
| --- | --- |
| `conversation_mode: "local"` | Local llama.cpp only; no Gemini generation |
| `gemini_live.response_voice: "piper"` | Default: Gemini text and local text share Piper |
| `gemini_live.response_voice: "native"` | Optional Gemini Live audio with `voice_name: "Charon"` |
| `gemini_live.text_model` | Cloud text model; defaults to `gemini-3.5-flash-lite` |
| `gemini_live.model` | Model used only for optional native Live audio |

Charon is the deeper native voice option selected for this portrait. It will still sound different from Piper. Use the default shared-Piper route when voice consistency matters most. The browser demo uses the operating system's speech voices and prefers a known masculine voice when available.

The cloud text default follows Google's current [model availability guidance](https://ai.google.dev/gemini-api/docs/deprecations): access to Gemini 2.5 is limited to existing users. All model names remain configurable.

Token quotas in `gemini_live` are best-effort application limits, **not a hard spending cap or a free-tier guarantee**. One in-flight response can exceed the remaining limit, and failed requests may not report complete usage. Check your provider's account limits separately.

## Responsiveness and graphics

- Generation, synthesis, and playback run as separate stages with bounded queues. Later phrases can be generated and synthesized while the current phrase plays.
- Whisper defaults to `tiny.en`, int8, and two CPU threads. Silence after speech ends a phrase after approximately 0.5 seconds; the initial listening window is four seconds.
- Piper keeps its Python voice loaded, primes the greeting, and caches up to 128 utterances. Missing speech models produce an actionable error instead of silently humming.
- The portrait defaults to 30 FPS, with cached images, labels, captions, and particles. Camera motion analysis runs at reduced resolution, and hidden camera previews are not copied.
- Main-thread state transitions reject stale microphone results, recover from failed turns, and wait for playback to finish before reopening the microphone.

The camera driver detects **motion on the CPU**. It can inspect Hailo SDK availability, but this repository does not currently run Hailo person inference. An AI HAT is optional; do not interpret motion triggers as reliable person recognition.

Controls: **Space** wake, **T** test question, **C** camera preview, **H** diagnostics, **Esc/Q** quit. `--fullscreen` applies to both normal and demo runs.

## Browser application

Use Node.js 22 or later. The browser frontend does not control the native Python process or use its JSON configuration.

```bash
npm ci
npm run dev
# Open http://localhost:3000

npm run lint
npm run build
npm start
```

`npm start` serves the built application without starting Vite. Microphone support and available voices depend on the browser/OS. Use Chrome or Edge for Web Speech recognition; typed input remains available. Browser microphone/camera access requires localhost or HTTPS. Without a Gemini key the browser returns scripted responses.

## Verification

```bash
python -m unittest discover -s tests
npm run lint
npm run build
python tools/benchmark_renderer.py --headless
```

On a headless Linux test machine, set `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy` for Python tests. Run the renderer benchmark without `--headless` on the Pi's actual display for useful deployment measurements.

The desktop headless renderer comparison (1024x768, 300 frames after warmup, diagnostics and camera preview disabled) measured median render work decreasing from **1.671 ms to 0.713 ms**. This excludes the frame-rate sleep and is not a Raspberry Pi benchmark or an end-to-end speech latency claim.

Before deployment, verify on the Pi: microphone phrase boundaries, first response delay with warm/cold models, audible local/cloud switching, speaker output, camera reconnects, and sustained temperature/CPU load. [Architecture](docs/architecture.md) documents the execution model and remaining limits.
