# Harry Potter Talking Portrait (Gemma 4 & Hailo AI)

An interactive, ultra-low-latency talking portrait application inspired by the enchanted portraits of Hogwarts. It combines 2D layered facial sprite rendering, optical camera presence triggers, speech recognition, local or cloud LLM intelligence (**Gemma 4 / Gemini**), low-latency **Piper TTS**, and audio-synchronized lip-flapping.

The project can be run in two modes:
1. **Interactive Web Application** (React 18 + Vite + Express backend + Canvas 2D + Web Speech + Gemini API).
2. **Native Python Edge System** (Pygame + faster-whisper + llama.cpp + Piper + Hailo-8/8L NPU for Raspberry Pi 5 & Desktop).

---

## Architecture Overview

```text
+-------------------------------------------------------------------------+
|                      Layered 2D Portrait Renderer                       |
|   Base (Neutral) + Blink Overlay (Eyes Closed) + 3 Audio Mouth Sprites  |
+-------------------------------------------------------------------------+
                                    ^
                                    | (Audio RMS Amplitudes, Visual State)
+-------------------------------------------------------------------------+
|                    Deterministic State Machine (FSM)                    |
|   IDLE -> WAKE_PENDING -> GREETING -> LISTENING -> THINKING             |
|                  -> SPEAKING -> LISTENING -> COOLDOWN                   |
+-------------------------------------------------------------------------+
       ^                   ^                     |               |
       | (Person Detection)| (Audio Transcript)  v (Prompt)      v (Speech Text)
+-------------+     +---------------+     +--------------+  +------------+
| Vision      |     | Speech-to-Text|     | Gemma 4 /    |  | Piper TTS  |
| (Hailo/Cam) |     | (Whisper/Web) |     | Gemini LLM   |  | (Audio RMS)|
+-------------+     +---------------+     +--------------+  +------------+
```

### 2D Layered Sprite Rendering Rules
- **Base Canvas Layer (`base.png`)**: Neutral portrait with open eyes and closed mouth.
- **Eyes Closed Overlay (`eyes_closed.png`)**: Transparent eyelid + glasses overlay blitted during 150ms blinks.
- **Mouth 1 Overlay (`mouth_1.png`)**: Closed resting mouth with beard/mustache ($\text{RMS} < 0.15$).
- **Mouth 2 Overlay (`mouth_2.png`)**: Slightly open mouth with visible teeth ($0.15 \le \text{RMS} < 0.45$).
- **Mouth 3 Overlay (`mouth_3.png`)**: Wide open mouth for loud vowels ($\text{RMS} \ge 0.45$).
- **1:1 Alignment**: All overlay layers share identical canvas dimensions, eliminating coordinate offset math.

---

## 1. Quick Start: Web Application (Desktop / Browser)

The web application runs a full-featured dashboard with animated Canvas physics, Facial Features Studio, live optical camera triggers, and telemetry.

### Prerequisites
- **Node.js**: v18.0.0 or higher
- **npm** or **bun** / **yarn**
- **Modern Browser**: Chrome, Edge, Safari, or Firefox (with Camera and Microphone access)

### Setup & Run

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment variables:**
   Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
   Add your Gemini API key (optional; built-in mock fallback will work if key is absent):
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```
   Open your browser to `http://localhost:3000`.

4. **Production build:**
   ```bash
   npm run build
   npm start
   ```

### Web Dashboard Controls & Hotkeys
- **`Spacebar`** or **Click Canvas**: Wake the portrait (simulates visitor presence).
- **`T` key**: Injects a test question to exercise the STT $\rightarrow$ Gemma $\rightarrow$ TTS pipeline.
- **`Esc` key**: Put the portrait to sleep (returns to `IDLE`).
- **Layer Inspector**: Upload custom image layers or test mouth shapes in real-time with the RMS slider.
- **Persona Preset Selector**: Switch between *Lord Cadogan (Photo Portrait)*, *Noble Alistair*, *Wilhelm the Trophy Fish*, and *Morgana the Witch*.

---

## 2. Desktop Setup: Native Python Engine (macOS / Windows / Linux)

Run the native Pygame application in demo mode on any desktop computer without needing specialized Raspberry Pi hardware.

### Prerequisites
- **Python**: 3.10, 3.11, or 3.12
- **PortAudio & SDL2** (usually included with Pygame and sounddevice)

### Installation

1. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On macOS / Linux:
   source venv/bin/activate
   # On Windows (PowerShell):
   venv\Scripts\Activate.ps1
   ```

2. **Install Python requirements:**
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-venv python3-pyaudio ffmpeg
   pip install -r requirements.txt
   ```

   On Raspberry Pi OS / Debian, do not mix `apt` and `pip` in one command. Install OS packages with `apt`, then activate your virtual environment and run `python -m pip install ...` separately.
   If you are using Raspberry Pi OS `python3-picamera2` from `apt` inside a `--system-site-packages` venv, keep `numpy` below `2.0` or `picamera2` can fail with a binary incompatibility error like `numpy.dtype size changed`.

3. **Run in Desktop Demo Mode:**
   ```bash
   python main.py --demo
   ```

### Desktop Demo Hotkeys
- **`Space`**: Simulate visitor approaching portrait (triggers vision detector).
- **`t`**: Injects test question (`"What great beasts have you slain, Sir Cadogan?"`).
- **`q`** or **`Esc`**: Clean exit.

### Connecting Local Gemma 4 via `llama.cpp` on Desktop (Optional)

1. Build `llama.cpp` or install `llama-server`.
2. Launch Gemma 4 E2B Instruction:
   ```bash
   llama-server -m models/gemma-4-e2b-instruction.Q4_K_M.gguf --port 8080 -c 2048
   ```
3. Run the Python application without demo mocks:
   ```bash
   python main.py
   ```

### Running Automated Test Suite
```bash
python -m unittest discover tests
```

---

## 3. Raspberry Pi 5 & Hailo AI HAT Deployment (Production Edge Build)

This setup runs the entire pipeline locally on a **Raspberry Pi 5** with hardware-accelerated vision, speech recognition, local LLM, and high-quality neural voice.

```text
Raspberry Pi 5 (8GB)
├── External SSD (500GB / ext4 mounted at /mnt/portrait)
├── Hailo-8L AI HAT (PCIe Gen 2 / Gen 3) -> YOLOv8 Person Detection (30 FPS, <5% CPU)
├── CSI Camera Module 3 -> Video capture
├── USB Microphone -> Audio input for faster-whisper
├── Bluetooth / 3.5mm Speaker -> Audio output for Piper TTS
└── HDMI Display (1080p / 720p Frame) -> Pygame KMS/DRM Fullscreen
```

### Step 1: External SSD Directory Setup & Permissions

Format or connect your external SSD and mount it to `/mnt/portrait`. Clarify mounting with forward slashes and ensure permissions are assigned to the current user immediately:

```bash
# 1. Mount the external SSD
sudo mkdir -p /mnt/portrait
sudo mount /dev/sda1 /mnt/portrait

# 2. Fix ownership permissions immediately for regular user operations
sudo chown -R $USER:$USER /mnt/portrait

# 3. Create model, cache, audio, and log directories on the SSD
mkdir -p /mnt/portrait/models/gemma
mkdir -p /mnt/portrait/models/stt
mkdir -p /mnt/portrait/models/piper
mkdir -p /mnt/portrait/models/hailo
mkdir -p /mnt/portrait/cache
mkdir -p /mnt/portrait/audio
mkdir -p /mnt/portrait/logs
```

### Step 2: Gemma 4 with `llama.cpp` (ARM64 NEON)

> **Note on Build Location**: To avoid symlink and shared library errors (`Operation not permitted`) caused by FAT32/exFAT or non-ext4 external SSDs, build `llama.cpp` directly in the user's home directory (`~/llama.cpp`). The compiled binary lives in `~/llama.cpp/build/bin/llama-server`, while model weights reside on the SSD.

1. **Build `llama.cpp` in the Home Directory (`~`):**
   ```bash
   cd ~
   git clone https://github.com/ggerganov/llama.cpp
   cd llama.cpp
   cmake -B build -DGGML_NATIVE=ON
   cmake --build build --config Release -j4
   ```

2. **Download Gemma 4 E2B Instruction GGUF to SSD (Direct Unsloth GGUF, No HF token needed):**
   ```bash
   wget -O /mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf \
     https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf
   ```

3. **Start `llama-server` (loading model from SSD):**
   ```bash
   ~/llama.cpp/build/bin/llama-server \
     -m /mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf \
     --port 8080 \
     --host 127.0.0.1 \
     -t 4 \
     -c 2048
   ```

### Step 3: Hailo AI HAT+ (13 TOPS / Hailo-8L) Vision Setup

1. **Enable PCIe in `/boot/firmware/config.txt`:**
   Add the following line to `/boot/firmware/config.txt`:
   ```ini
   dtparam=pciex1
   ```
   Save the file and reboot the Raspberry Pi:
   ```bash
   sudo reboot
   ```

2. **Install Hailo runtime and Python bindings:**
   ```bash
   sudo apt update
   sudo apt install -y hailo-all python3-hailort python3-picamera2
   ```

3. **Verify Hailo-8L device detection:**
   ```bash
   hailortcli scan
   ```

4. **Download the Hailo-8L compatible YOLOv8 Person Detection model from the Hailo Model Zoo:**
   ```bash
   wget -O /mnt/portrait/models/hailo/yolov8s_person.hef \
     https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.13.0/hailo8l/yolov8s.hef
   ```

### Step 4: Piper TTS Setup

1. **Download and unpack the arm64 Piper binary and voice model:**
   ```bash
   # Ensure SSD permissions are intact
   sudo chown -R $USER:$USER /mnt/portrait

   cd /mnt/portrait/models/piper
   wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz
   tar -xzf piper_arm64.tar.gz
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json
   ```

### Step 5: Configuration (`portrait_config.json`)

Verify `/mnt/portrait` paths in `portrait_config.json`:
```json
{
  "hardware": {
    "target": "raspberry_pi_5",
    "storage_mount_path": "/mnt/portrait",
    "models_dir": "/mnt/portrait/models",
    "cache_dir": "/mnt/portrait/cache",
    "audio_dir": "/mnt/portrait/audio",
    "logs_dir": "/mnt/portrait/logs"
  },
  "vision": {
    "driver": "hailo",
    "confidence_threshold": 0.55
  },
  "llm": {
    "driver": "llama_client",
    "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions",
    "model_name": "gemma-4-e2b-instruction",
    "timeout_seconds": 90.0
  },
  "stt": {
    "driver": "local_stt",
    "microphone_device_index": null,
    "microphone_name": "",
    "sample_rate": null
  },
  "tts": {
    "driver": "piper",
    "piper_binary_path": "/mnt/portrait/models/piper/piper",
    "model_path": "/mnt/portrait/models/piper/en_US-ryan-high.onnx",
    "audio_driver": "auto",
    "playback_sample_rate": 22050,
    "playback_channels": 1
  }
}
```

### Step 6: Running the Portrait on Pi 5

```bash
python main.py --fullscreen --config portrait_config.json
```

### Step 7: Auto-Start on Boot (systemd Service)

Create `/etc/systemd/system/portrait.service`:
```ini
[Unit]
Description=Harry Potter Talking Portrait
After=network.target sound.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/talking-portrait
ExecStart=/usr/bin/python3 /home/pi/talking-portrait/main.py --fullscreen --config portrait_config.json
Restart=always
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable portrait.service
sudo systemctl start portrait.service
```

---

## 4. Latency Benchmarks & Turnaround Budget

| Subsystem | Processing Time | Mechanism |
| :--- | :--- | :--- |
| **STT (Speech to Text)** | ~0.55s – 0.65s | faster-whisper `tiny.en` on 4 CPU threads |
| **Gemma 4 Time-to-First-Token** | ~0.70s – 0.80s | `llama.cpp` 4-bit quantized (Q4_K_M) |
| **Gemma 4 Generation** | ~18 – 22 tok/s | ~25 tokens generated (1.1s total) |
| **Piper TTS First Audio** | ~0.25s – 0.35s | Streaming sentence-chunk synthesis |
| **Total Conversational Turn** | **~1.3s – 1.6s** | **Natural, human-paced responsive dialogue** |

---

## 5. Troubleshooting & FAQ

### Web Application Issues
- **Microphone / Camera permission blocked**: In browser address bar, click the site permissions icon and allow Microphone and Camera.
- **Port 3000 in use**: Stop any existing instance with `kill $(lsof -t -i:3000)` before restarting `npm run dev`.
- **Speech recognition not supported in browser**: Chrome and Edge natively support the Web Speech API. For other browsers, typing questions or demo mode works out-of-the-box.

### Raspberry Pi 5 Hardware Issues
- **Hailo device not found (`hailortcli scan` empty)**: Check PCIe ribbon cable orientation, ensure `dtparam=pciex1` is in `/boot/firmware/config.txt`, and reboot.
- **Microphone not detected**: Run `python tools/diagnose_audio.py` or `python -c "import speech_recognition as sr; print(list(enumerate(sr.Microphone.list_microphone_names())))"` and set `stt.microphone_device_index` or `stt.microphone_name` in `portrait_config.json`.
- **Only a humming tone plays instead of speech**: Piper was not found or failed, so the app used the synthetic fallback. Verify the Piper binary exists under `/mnt/portrait/models/piper/` and watch for `[TTS] Using synthetic fallback audio` in the logs.
- **Audio playback sounds distorted on Pi speakers**: Keep `tts.playback_sample_rate` at `22050` and `tts.playback_channels` at `1`, since Piper outputs 22.05 kHz mono WAV audio.
- **llama-server seems up but replies still fail**: First verify it is actually listening with `curl http://127.0.0.1:8080/v1/models`. If that works, increase `llm.timeout_seconds` if the Pi is still prompt-processing when the client disconnects. A cancellation in the llama-server terminal after 10-20 seconds usually means the client timed out.
- **Pygame display errors without desktop GUI**: Use SDL DirectFB/KMSDRM mode by setting `export SDL_VIDEODRIVER=kmsdrm` before launching `main.py`.

---

## License & Credits

- Inspired by the enchanted portraits of the Harry Potter universe.
- Powered by **Google Gemma 4**, **Hailo AI**, **Rhasspy Piper**, and **Vite + React**.
