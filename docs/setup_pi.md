# Raspberry Pi 5 & Hailo AI HAT Deployment Guide

This guide details setting up the **Harry Potter Talking Portrait** on a Raspberry Pi 5 with an external Samsung SSD, Hailo AI HAT, Pi Camera, USB Microphone, and Bluetooth audio.

## Hardware Connections

1. **Raspberry Pi 5**: 8GB recommended.
2. **Hailo AI HAT**: Installed on the PCIe slot.
3. **External SSD**: Formatted (ext4) and mounted at `/mnt/portrait`.
4. **Display**: HDMI connected to Pi 5 (running full-screen 1080p or 720p).
5. **Camera**: Raspberry Pi Camera Module 3 attached via CSI ribbon cable.
6. **Microphone**: USB microphone.
7. **Audio Output**: Bluetooth speaker or 3.5mm DAC.

---

## 1. External SSD Directory Structure & Permissions

Set up the directory hierarchy on the external SSD mounted at `/mnt/portrait`:

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

---

## 2. Setting Up Gemma 4 with llama.cpp on Pi 5

> **Note on Build Location**: Build `llama.cpp` in the user's home directory (`~/llama.cpp`) to avoid symlink and shared library permissions errors on non-ext4 filesystems. Model weights reside on the SSD.

Compile and install `llama.cpp` for ARM64 with NEON acceleration:

```bash
cd ~
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DGGML_NATIVE=ON
cmake --build build --config Release -j4
```

Download the quantized Gemma 4 E2B Instruction GGUF model directly via Unsloth (no HF authentication required):
```bash
wget -O /mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf \
  https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf
```

Start the persistent `llama-server` background service:
```bash
~/llama.cpp/build/bin/llama-server \
  -m /mnt/portrait/models/gemma/gemma-4-e2b-instruction.Q4_K_M.gguf \
  --port 8080 \
  --host 127.0.0.1 \
  -t 4 \
  -tb 4 \
  -c 512 \
  -np 1 \
  -b 256 \
  -ub 256 \
  --flash-attn on \
  --reasoning off \
  --reasoning-budget 0 \
  --no-webui
```

---

## 3. Setting Up Hailo AI HAT+ (13 TOPS / Hailo-8L)

1. Enable PCIe in `/boot/firmware/config.txt`:
   ```ini
   dtparam=pciex1
   ```
   Save and reboot the Pi:
   ```bash
   sudo reboot
   ```
2. Install Hailo runtime packages and Python bindings:
   ```bash
   sudo apt update && sudo apt install -y hailo-all python3-hailort python3-picamera2
   ```
3. Verify device detection:
   ```bash
   hailortcli scan
   ```
4. Download the Hailo-8L compatible YOLOv8 Person Detection model:
   ```bash
   wget -O /mnt/portrait/models/hailo/yolov8s_person.hef \
     https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v2.13.0/hailo8l/yolov8s.hef
   ```

---

## 4. Setting Up Piper TTS

1. Download the Piper arm64 binary and voice models:
   ```bash
   sudo chown -R $USER:$USER /mnt/portrait
   cd /mnt/portrait/models/piper
   wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz
   tar -xzf piper_arm64.tar.gz
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json
   ```

---

## 5. Running the Application on Boot

Launch the portrait in full-screen production mode:

```bash
python main.py --fullscreen --config portrait_config.json
```

Or configure a systemd service (`/etc/systemd/system/portrait.service`) to auto-start on display login.
