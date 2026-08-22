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

## 1. External SSD Directory Structure

Set up the directory hierarchy on the external 500GB SSD:

```bash
sudo mkdir -p /mnt/portrait/models/gemma
sudo mkdir -p /mnt/portrait/models/stt
sudo mkdir -p /mnt/portrait/models/piper
sudo mkdir -p /mnt/portrait/models/hailo
sudo mkdir -p /mnt/portrait/cache
sudo mkdir -p /mnt/portrait/audio
sudo mkdir -p /mnt/portrait/logs

sudo chown -R $USER:$USER /mnt/portrait
```

---

## 2. Setting Up Gemma 4 with llama.cpp on Pi 5

Compile and install `llama.cpp` for ARM64 with NEON acceleration:

```bash
cd /mnt/portrait
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DGGML_NATIVE=ON
cmake --build build --config Release -j4
```

Download the quantized Gemma 4 E2B Instruct GGUF model:
```bash
wget -O /mnt/portrait/models/gemma/gemma-4-e2b-instruct.Q4_K_M.gguf <MODEL_DOWNLOAD_URL>
```

Start the persistent `llama-server` background service:
```bash
/mnt/portrait/llama.cpp/build/bin/llama-server \
  -m /mnt/portrait/models/gemma/gemma-4-e2b-instruct.Q4_K_M.gguf \
  --port 8080 \
  -c 2048 \
  --threads 4 \
  --host 127.0.0.1
```

---

## 3. Setting Up Hailo AI HAT

1. Ensure Raspberry Pi OS has the Hailo kernel drivers enabled in `/boot/firmware/config.txt`:
   ```ini
   dtparam=pciex1
   ```
2. Install Hailo runtime packages:
   ```bash
   sudo apt install hailo-all python3-hailort
   ```
3. Verify device detection:
   ```bash
   hailortcli scan
   ```
4. Place the YOLOv8 person detection HEF model at:
   `/mnt/portrait/models/hailo/yolov8s_person.hef`

---

## 4. Setting Up Piper TTS

1. Download the Piper arm64 binary:
   ```bash
   cd /mnt/portrait/models/piper
   wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz
   tar -xzf piper_arm64.tar.gz
   ```
2. Download the `en_US-ryan-high` voice model & config:
   ```bash
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json
   ```

---

## 5. Running the Application on Boot

Launch the portrait in full-screen production mode:

```bash
python main.py --fullscreen --config portrait_config.json
```

Or configure a systemd service (`/etc/systemd/system/portrait.service`) to auto-start on display login.
