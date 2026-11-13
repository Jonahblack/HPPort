# Project Rules: Harry Potter Talking Portrait (Wilhelm)

These rules apply to all agents, swarm workers, and subagents working in this codebase. Follow them strictly to maintain system stability, performance, and narrative authenticity.

---

## 1. Grounding & Architectural Philosophy

1. **Physical Reality vs. Conversational State:**
   - The **Physical Scene Director** ([`renderer/scene_director.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/renderer/scene_director.py)) strictly governs the physical environment (poses, props: book, tinker box, empty room). Never force-cut between incompatible physical scenes or invent missing transition footage.
   - The **State Machine** ([`state_machine.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/state_machine.py)) strictly governs conversational turns (`IDLE`, `WAKE_PENDING`, `GREETING`, `LISTENING`, `THINKING`, `SPEAKING`, `COOLDOWN`).
   - All state transitions and UI rendering occur on the main display thread. Background workers communicate strictly via thread-safe queues or event posts (`_post` in [`main.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/main.py)).

2. **The "Living Portrait" Principle (No Freeze-Frames):**
   - In conversation (`GREETING`, `LISTENING`, `THINKING`, `SPEAKING`), Wilhelm must **never** be a motionless photograph.
   - Even when holding the final frame of an engagement video (`engaged_book` or `engaged_tinker`), the renderer must dynamically articulate:
     - Preston-Blair or amplitude-driven mouth visemes during speech.
     - Biological eyelid blinks with natural easing (180ms ease-in/out every 2.5–5.5s).
     - Visitor gaze tracking and micro-saccades (1–2px ocular tremor).
     - Sinusoidal chest breathing drift (2–3px vertical offset).
   - Subtitles remain enabled for debugging per user direction.
   - Transition clip pacing remains at full length until the user requests adjustments.

3. **Hardware Boundaries & Performance (Raspberry Pi 5):**
   - The deployment target is Raspberry Pi 5 (quad-core ARM Cortex-A76 @ 2.4 GHz, no discrete GPU).
   - Development and testing run on Windows and desktop Linux. Code must be cross-platform.
   - **Never block the main display thread.** Heavy tasks (speech-to-text, LLM generation, Piper TTS synthesis, video decoding) must run on bounded worker threads.
   - Keep memory budgets bounded: decode frames at configured `decode_width` (default 960) and release Pygame surfaces promptly.

---

## 2. Codebase Organization & Ownership Boundaries

To avoid collision among swarm workers, respect these module boundaries:

| Subsystem | Primary Files | Scope & Responsibilities |
| :--- | :--- | :--- |
| **Visual Rig & Renderer** | [`renderer/renderer.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/renderer/renderer.py), [`renderer/animation.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/renderer/animation.py) | Display loop, viseme blitting on held video frames, gaze/saccades, blinks, dust motes. |
| **Scene Director & Graph** | [`renderer/scene_director.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/renderer/scene_director.py), [`wilhelm_asset_manifest.json`](file:///c:/Users/jonah/Documents/Atlas/HPPort/wilhelm_asset_manifest.json) | Graph routing, clip queuing, activity switching, day/night schedule. |
| **Speech & Audio Pipeline**| [`speech_pipeline.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/speech_pipeline.py), [`tts/piper.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/tts/piper.py), [`tts/`](file:///c:/Users/jonah/Documents/Atlas/HPPort/tts/) | Bounded speech pipeline, instant thinking fillers, Piper TTS caching and synthesis. |
| **State & Lifecycle** | [`state_machine.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/state_machine.py), [`main.py`](file:///c:/Users/jonah/Documents/Atlas/HPPort/main.py) | Conversational FSM, presence-loss recovery, turn coordination, graceful error handling. |
| **Verification & Tests** | [`tests/`](file:///c:/Users/jonah/Documents/Atlas/HPPort/tests/), [`tools/`](file:///c:/Users/jonah/Documents/Atlas/HPPort/tools/) | Unit tests, headless benchmarks, async mock fixes, regression validation. |

---

## 3. Engineering & Testing Standards

1. **Headless Test Execution:**
   - Always set `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy` when executing tests.
   - Python command on Windows: `& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m unittest discover -s tests`.
2. **No Regression Rule:**
   - All tests in `tests/` must pass before any work is deemed ready.
   - Existing mock test harnesses (such as `test_live_client.py` and `test_stt_tts.py`) must be kept functional without blocking or infinite loops.
3. **Safe Imports:**
   - Optional hardware libraries (e.g. `picamera2`, `pyaudio`, `SpeechRecognition`, Hailo SDK) must be imported conditionally with graceful mock fallbacks.
