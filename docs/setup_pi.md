# Raspberry Pi setup

Use a Raspberry Pi 5 with 64-bit Raspberry Pi OS, active cooling, an HDMI display, microphone, and speakers. An 8 GB model and SSD provide more room for local models. USB or wired audio generally avoids the extra latency of Bluetooth. The Pi 5 has no built-in 3.5 mm audio jack; use USB, HDMI, Bluetooth, or an audio DAC.

The camera currently uses CPU motion detection. A Hailo AI HAT is not required and will not accelerate Whisper, llama.cpp, or Piper in this implementation.

## 1. Environment

Run from the project directory:

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev python3-pyaudio \
  python3-picamera2 libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 \
  libsdl2-ttf-2.0-0 alsa-utils ffmpeg
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-piper.txt
```

Use the system Python with `--system-site-packages` so apt's Picamera2/libcamera bindings remain visible. Raspberry Pi OS requires pip packages to be installed in a virtual environment; see [the OS documentation](https://www.raspberrypi.com/documentation/computers/os.html).

Bookworm's Python 3.11 camera stack needs NumPy 1.x. The requirements preserve that constraint and cap OpenCV below the release that forces NumPy 2. Python 3.13 uses NumPy 2.x wheels; do not mix a newer Python runtime with older OS camera bindings. Use a fresh venv if an existing environment already has incompatible NumPy/OpenCV packages.

## 2. Storage and local model

Mount your existing SSD at `/mnt/portrait` using your normal mount configuration. Confirm this is the intended disk before creating directories. The app user needs write access to its cache, audio, and model-download directories.

```bash
mkdir -p /mnt/portrait/models/{gemma,stt,piper}
mkdir -p /mnt/portrait/{cache,audio,logs}
```

If no SSD is mounted, change all `hardware`/`tts` paths in `portrait_config.json` to writable directories on the Pi. Do not run the portrait as root to work around permissions.

Run an ARM64 build of [llama.cpp](https://github.com/ggml-org/llama.cpp) and a compatible instruction-tuned GGUF model. Keep an existing working model; the app discovers the server's model ID. The current configuration uses Gemma 4 E2B. Point the command at the file you actually downloaded:

```bash
~/llama.cpp/build/bin/llama-server \
  -m /mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  -t 3 -tb 3 -c 1024 -np 1 -b 128 -ub 128 \
  --reasoning off --reasoning-budget 0 --no-webui
```

These are starting settings, not a measured optimum. Three inference threads leave CPU capacity for audio and the display. Benchmark your model; a smaller quantized model may improve response time more than application tuning. Check your installed `llama-server --help` for supported flags. Increase context size if your system prompt/history needs more space. Hidden reasoning can exhaust short output limits, so disable it for this short spoken persona when the model/server supports that setting.

Whisper downloads `tiny.en` on first use into `hardware.models_dir/stt` by default. To run entirely offline, let that download finish first, or set `stt.model_size` to a local faster-whisper model directory. Set `stt.local_files_only: true` after the files are cached if you want missing files to fail without downloading.

## 3. Piper voice

Download the voice and matching config:

```bash
cd /mnt/portrait/models/piper
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json
```

`requirements-piper.txt` installs the optional [Piper Python runtime](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md), which retains the voice in memory. Leave `tts.runtime: "auto"` to use it when available. If using an existing standalone arm64 Piper installation, set `tts.piper_binary_path` to its executable and optionally `runtime: "cli"`. Extracted archives may have an extra `piper/` directory; executable discovery handles that layout.

The default greeting warms the cache at startup. Cached utterances are capped at 128. If both Python and CLI synthesis fail, the application reports an error and enters cooldown. Synthetic tones are confined to demo mode unless you explicitly enable `tts.allow_synthetic_fallback`.

## 4. Voice routes and microphone

From the project directory, copy `.env.example` to `.env` and set `GEMINI_API_KEY` for optional cloud responses. The native app reads `.env` beside its configuration file; environment variables take precedence. Use `conversation_mode: "local"` for offline inference.

Keep `gemini_live.response_voice: "piper"` for identical speech synthesis across models. To audition Gemini's own Charon voice, set it to `"native"`; native cloud audio and local Piper have distinct timbres. `gemini_live.text_model` and `gemini_live.model` select text and native-audio models independently.

Audio defaults use the operating system's selected input device rather than a hard-coded ALSA card number. If needed, select a stable microphone name with `stt.microphone_name`. Use `stt.arecord_device` only when the PortAudio input route is unavailable and the arecord fallback needs an explicit ALSA device.

```bash
arecord -l
aplay -l
python tools/diagnose_audio.py --help
```

`state_machine.silence_timeout_seconds` is the initial wait for someone to speak (four seconds). `stt.pause_threshold` is the silence *after speech* that ends the phrase (0.5 seconds). Increase the latter for speakers who pause often. `max_listen_duration_seconds` caps a spoken phrase at ten seconds. Leave `stt.allow_online_fallback: false` for predictable local transcription.

## 5. Start and verify

From the project directory with the venv active:

```bash
python main.py --fullscreen --config portrait_config.json
```

Test **T** for a response without camera/microphone input. Use **Space** to simulate presence, **C** for the camera preview, and **H** for latency diagnostics. Verify microphone input after the greeting and after several consecutive replies. Test local mode, cloud mode, quota/network fallback, and shutdown during playback.

The `stt` HUD value includes waiting/capture and transcription. `llm_ttft` measures the first speakable clause, not the first raw token. `turnaround` measures completed transcript to actual playback, including synthesis; it excludes the time spent recording the user. These distinctions matter when comparing recordings with displayed timing.

```bash
python tools/benchmark_renderer.py
```

Run that benchmark on the actual Pi display to measure render work without the frame-rate sleep. Check temperatures and CPU use during several minutes of conversation. Lower `renderer.width`/`height` if necessary, and keep diagnostics/camera overlays off for the normal experience.

## 6. Optional desktop autostart

Start from a logged-in graphical desktop first. A system-wide service with a hard-coded user, system Python, or missing audio/display session often fails even when a terminal run works.

For desktop autostart, create a `.desktop` entry in `~/.config/autostart/` using absolute paths for your checkout and venv:

```ini
[Desktop Entry]
Type=Application
Name=Talking Portrait
Path=/home/YOUR_USER/HPPort
Exec=/home/YOUR_USER/HPPort/.venv/bin/python /home/YOUR_USER/HPPort/main.py --fullscreen
Terminal=false
```

Replace `YOUR_USER` and the checkout path. Start llama-server separately before relying on local inference. Console-only KMS/DRM startup and systemd display/audio-session integration depend on your OS/session and are not validated by the desktop tests.
