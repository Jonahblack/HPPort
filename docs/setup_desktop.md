# Desktop Setup & Development Guide

This guide describes how to develop and test the **Harry Potter Talking Portrait** on a desktop PC (Windows, macOS, or Linux) using Demo Mode without requiring Raspberry Pi hardware or Hailo AI HAT.

## Prerequisites

- Python 3.10+
- (Optional) `llama.cpp` if running local Gemma 4 inference on desktop.

## Installation

1. Clone or open the repository:
   ```bash
   cd talking-portrait
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

## Running in Desktop Demo Mode

Launch the application with the `--demo` flag:

```bash
python main.py --demo
```

### Desktop Controls in Demo Mode:
- **`Spacebar`**: Simulates a visitor approaching the portrait (triggers vision detector).
- **`t`**: Injects sample spoken dialogue to test STT -> Gemma -> Piper -> Mouth Flapping.
- **`Esc` or `q`**: Cleanly shuts down the application.

## Testing with Local llama.cpp (Gemma 4 E2B Instruction)

If you have `llama-server` installed on your desktop:

1. Download the Gemma 4 E2B Instruction GGUF model:
   ```bash
   # Place in your local models folder
   llama-server -m models/gemma-4-e2b-instruction.Q4_K_M.gguf --port 8080 -c 2048
   ```

2. In `portrait_config.json`, ensure:
   ```json
   "llm": {
     "driver": "llama_client",
     "endpoint_url": "http://127.0.0.1:8080/v1/chat/completions"
   }
   ```

3. Run without mock LLM:
   ```bash
   python main.py
   ```

## Running Unit Tests

Verify all modular components and state machine transitions:

```bash
python -m unittest discover tests
```
