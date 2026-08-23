# System Architecture & Design Specification

## Overview

The **Harry Potter Talking Portrait** is a low-latency, modular edge-computing system designed to run on a Raspberry Pi 5 with Hailo AI HAT. It presents an animated Victorian/Hogwarts knight portrait (Lord Cadogan) that naturally wakes up when people approach, greets them, engages in conversational speech using **Gemma 4**, synchronizes realistic mouth flapping with generated audio waveforms, and returns to an idle ambient state.

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
| **TTS** | `BaseTTS` | `PiperTTS` (ryan-high ONNX) | `MockTTS` (Synthetic Wave) |
| **Renderer** | `PortraitRenderer` | Pygame (Full-screen KMS/DRM) | Pygame Windowed |

---

## 2. Low-Latency Pipeline & Instrumentation

Latency target: **1.0s – 2.0s total turn-around** from user speech completion to portrait audio playback.

The system instruments and logs every stage of the pipeline:

```text
STT:                 0.62 s
LLM first token:     0.74 s
LLM generation:      9.2 tok/s
First phrase ready:  1.14 s
TTS first audio:     0.31 s
Response started:    1.45 s
```

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
│   │   ├── en_US-ryan-high.onnx
│   │   └── en_US-ryan-high.onnx.json
│   └── hailo/
│       └── yolov8s_person.hef
├── cache/
├── audio/
└── logs/
```
