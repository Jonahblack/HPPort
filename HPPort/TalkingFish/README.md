# TalkingFish (fixed)
Wake-word activated Gemini chatty fish named **Wilhelm**. Runs on a Raspberry Pi 3.

## Quick start
1. Put your Google Cloud service account JSON on the Pi and point `GOOGLE_APPLICATION_CREDENTIALS` to it.
2. Export your Gemini API key as `GEMINI_API_KEY`.
3. `sudo apt-get install -y libasound2-dev portaudio19-dev`
4. `pip3 install -r requirements.txt`
5. Plug in a USB mic and speaker (or 3.5mm output) and run `python3 fishai.py`.

Say **“wilhelm”** to start the conversation. Say **“goodbye wilhelm”** to end it.
