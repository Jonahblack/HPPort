# System Architecture & Design Specification

## Overview

The **Harry Potter Talking Portrait** is a low-latency, modular edge-computing system designed to run on a Raspberry Pi 5 with Hailo AI HAT. It presents an animated Victorian/Hogwarts knight portrait (Wilhelm) that naturally wakes up when people approach, greets them, engages in conversational speech using **Gemma 4**, synchronizes realistic mouth flapping with generated audio waveforms, and returns to an idle ambient state.

```text
+-------------------------------------------------------------+
|                      Pygame Renderer                        |
|  (Base Portrait + Blinking Eyelids + Synchronized Flapping) |
+-------------------------------------------------------------+
                              ^
                              | (amplitudes, state events)
+-------------------------------------------------------------+
|                 Explicit State Machine (FSM)                |
|  IDLE -> WAKE_PENDING -> GREETING -> LISTENING -> THINKING  |
|             -> SPEAKING -> LISTENING -> COOLDOWN            |
+-------------------------------------------------------------+
   ^               ^                       |              |
   | (frames)      | (text)                v (query)      v (text)
+---------+   +----------+           +-----------+   +----------+
| Vision  |   |   STT    |           |   Gemma   |   |   TTS    |
| (Hailo) |   | (Whisper)|           | (llama.cpp|   | (Piper)  |
+---------+   +----------+           +-----------+   +----------+
```

---

## 1. Modular Subsystem Interfaces

All hardware-dependent and backend components are abstracted behind interfaces:

| Subsystem | Abstract Base | Raspberry Pi 5 Implementation | Desktop Demo / Mock |
| :--- | :--- | :--- | :--- |
| **Vision** | `BaseVisionDetector` | `HailoVision` (Hailo-8L NPU) | `MockVision` (Space / Timer) |
| **STT** | `BaseSTT` | `LocalSTT` (faster-whisper) | `KeyboardSTT` (UI / CLI) |
| **LLM** | `BaseLLMClient` | `LlamaClient` (Gemma 4 E2B) | `MockLLMClient` (Scripted) |
| **TTS** | `BaseTTS` | `PiperTTS` (ryan-medium ONNX) | `MockTTS` (Synthetic Wave) |
| **Renderer** | `PortraitRenderer` | Pygame (Full-screen KMS/DRM) | Pygame Windowed |

---

---

## 2. Dual-Mode Hybrid Architecture (Local Fast Path & Gemini Live)

The system operates in an **offline-first hybrid mode**:
1. **Gemini Live API (Online / Low-Latency Voice)**: When connected to the internet and within free tier token limits, provides ultra-low latency (~400–600ms) bidirectional audio conversation with expressive British knight inflection (voice: `Puck`).
2. **Token Safeguard Manager (`TokenSafeguard`)**: Intercepts `usage_metadata` on every turn, tracks daily/session tokens against user quotas (e.g. 250,000/day), persists state across reboots in `token_usage.json`, and enforces an immediate, hard cutoff and graceful spoken transition to local mode when limits are hit.
3. **Accelerated Local Offline Pipeline**:
   - **Streaming VAD**: Real-time RMS chunk monitoring terminates audio recording within **350ms** of user silence (eliminating the old 10s `arecord` wait).
   - **Streaming LLM**: Real-time SSE token delivery via `llama-server`.
   - **Clause Pipelining**: Chunks text on clause boundaries (3–6 words) and feeds them to Piper in ~150ms slices, beginning speech playback on clause 1 while clause 2 is still generating.

| Mode | Audio Input | Intelligence & TTS | Turnaround Latency | Quota / Internet |
| :--- | :--- | :--- | :--- | :--- |
| **Gemini Live** | 16kHz PCM Mic Stream | Gemini 3.1 Flash Live (Native Audio) | **~0.4s – 0.6s** | Internet + Token Safeguard |
| **Local Pipelined** | Streaming VAD (350ms) | llama.cpp Stream -> Piper Clause Chunk | **~1.2s – 1.8s** | 100% Offline (Zero Cloud) |

### Mouth Synchronization Formula:
Calculates normalized RMS power of 16-bit audio in ~33ms video slices:

$$\text{RMS} = \sqrt{\frac{1}{N}\sum_{i=1}^{N} x_i^2}$$

- $\text{RMS} < 0.15 \rightarrow \text{mouth\_1.png (Closed)}$
- $0.15 \le \text{RMS} < 0.45 \rightarrow \text{mouth\_2.png (Partial)}$
- $\text{RMS} \ge 0.45 \rightarrow \text{mouth\_3.png (Wide)}$

---

## 3. External SSD Layout (`/mnt/portrait`)

```text
/mnt/portrait/
├── models/
│   ├── gemma/
│   │   └── gemma-4-e2b-instruction.Q4_K_M.gguf
│   ├── stt/
│   │   └── faster_whisper_tiny_en/
│   ├── piper/
│   │   ├── piper (arm64 binary)
│   │   ├── en_US-ryan-medium.onnx
│   │   └── en_US-ryan-medium.onnx.json
│   └── hailo/
│       └── yolov8s_person.hef
├── cache/
├── audio/
└── logs/
```
