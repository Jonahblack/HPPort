#!/usr/bin/env python3
"""Harry Potter Talking Portrait - Gemma 4 on Raspberry Pi 5 with Hailo AI HAT.

Main entry point integrating Vision (Hailo-8L), STT (faster-whisper), LLM (Gemma 4 via llama.cpp),
TTS (Piper), Finite State Machine, and Pygame portrait lip-sync renderer.
"""

import os
import sys
import time
import threading
import pygame
from typing import Optional

from config import load_config, parse_args
from state_machine import PortraitStateMachine, PortraitState

from vision.hailo import HailoVision
from vision.mock import MockVision
from stt.local_stt import LocalSTT
from stt.keyboard_stt import KeyboardSTT
from llm.llama_client import LlamaClient
from llm.mock_client import MockLLMClient
from tts.piper import PiperTTS
from tts.mock_tts import MockTTS
from renderer.renderer import PortraitRenderer


class TalkingPortraitApp:
    """Master application controller."""

    def __init__(self, config_path: str = "portrait_config.json", demo_mode: bool = False):
        self.config = load_config(config_path, demo_mode=demo_mode)
        self.demo_mode = demo_mode

        # Initialize State Machine
        self.fsm = PortraitStateMachine(self.config, on_state_change=self._on_state_change)

        # Initialize Vision
        vision_driver = self.config["vision"].get("driver", "hailo")
        if vision_driver == "hailo" and not demo_mode:
            self.vision = HailoVision(self.config)
        else:
            self.vision = MockVision(self.config)

        # Initialize STT
        stt_driver = self.config["stt"].get("driver", "local_stt")
        if stt_driver == "local_stt" and not demo_mode:
            self.stt = LocalSTT(self.config)
        else:
            self.stt = KeyboardSTT(self.config)

        # Initialize LLM
        llm_driver = self.config["llm"].get("driver", "llama_client")
        if llm_driver == "llama_client" and not demo_mode:
            self.llm = LlamaClient(self.config)
        else:
            self.llm = MockLLMClient(self.config)

        # Initialize TTS
        tts_driver = self.config["tts"].get("driver", "piper")
        if tts_driver == "piper" and not demo_mode:
            self.tts = PiperTTS(self.config)
        else:
            self.tts = MockTTS(self.config)

        # Initialize Renderer
        self.renderer = PortraitRenderer(self.config)

        # Runtime control variables
        self.running = True
        self.conversation_history = []
        self.current_audio_thread: Optional[threading.Thread] = None

    def _on_state_change(self, new_state: PortraitState) -> None:
        """Handle state change side-effects."""
        self.renderer.set_state(new_state)

        if new_state == PortraitState.GREETING:
            greeting_prompt = self.config["llm"].get(
                "greeting_prompt",
                "Ah, a visitor arrives before my frame! State your business, noble wanderer!"
            )
            self._speak_phrase(greeting_prompt, on_complete=self.fsm.on_greeting_complete)

        elif new_state == PortraitState.LISTENING:
            self.renderer.set_subtitle("Listening for your voice...")
            # Spawn worker thread for listening
            threading.Thread(target=self._listen_worker, daemon=True).start()

        elif new_state == PortraitState.IDLE:
            self.renderer.set_subtitle("")
            self.renderer.set_audio_amplitude(0.0)

        elif new_state == PortraitState.COOLDOWN:
            self.renderer.set_subtitle("Resting peacefully in the castle hall...")
            self.renderer.set_audio_amplitude(0.0)

    def _listen_worker(self) -> None:
        """Background worker to listen for user speech."""
        if self.fsm.state != PortraitState.LISTENING:
            return

        user_text = self.stt.listen_and_transcribe(timeout_seconds=3.0, max_duration_seconds=10.0)

        if user_text and user_text.strip():
            print(f"[STT] User said: \"{user_text}\"")
            self.fsm.on_speech_detected()
            self._generate_and_speak(user_text)
        else:
            self.fsm.on_speech_silence()

    def _generate_and_speak(self, user_text: str) -> None:
        """Generate LLM response and speak it."""
        self.renderer.set_subtitle("Lord Cadogan is pondering...")

        start_time = time.time()
        reply = self.llm.generate_response(
            user_message=user_text,
            conversation_history=self.conversation_history,
        )
        llm_latency = time.time() - start_time

        # Update history
        self.conversation_history.append({"role": "user", "content": user_text})
        self.conversation_history.append({"role": "assistant", "content": reply})

        print(f"[Pipeline] LLM Response generated in {llm_latency:.2f}s")
        self.fsm.on_llm_response_ready()
        self._speak_phrase(reply, on_complete=self.fsm.on_speaking_complete)

    def _speak_phrase(self, text: str, on_complete: Optional[callable] = None) -> None:
        """Synthesize audio and play with mouth synchronization."""
        def worker():
            cache_dir = self.config.get("hardware", {}).get("cache_dir", "/mnt/portrait/cache")
            audio_dir = self.config.get("hardware", {}).get("audio_dir", cache_dir)
            if not os.path.exists(audio_dir):
                audio_dir = "/tmp"

            wav_path = os.path.join(audio_dir, f"speech_{int(time.time()*1000)}.wav")

            synth_start = time.time()
            out_path, duration = self.tts.synthesize_to_file(text, wav_path)
            synth_latency = time.time() - synth_start

            print(f"[Pipeline] TTS Synthesized in {synth_latency:.2f}s (Audio length: {duration:.2f}s)")
            self.renderer.set_subtitle(text)

            # Analyze lip sync amplitudes
            amplitudes = self.renderer.lipsync_engine.analyze_wav(out_path, fps=self.renderer.fps)

            # Play audio using pygame.mixer
            try:
                sound = pygame.mixer.Sound(out_path)
                sound.play()
            except Exception as e:
                print(f"[Audio] Pygame sound play warning: {e}")

            # Animate mouth flap across duration
            frame_duration = 1.0 / self.renderer.fps
            for amp in amplitudes:
                if not self.running or self.fsm.state not in (PortraitState.GREETING, PortraitState.SPEAKING):
                    break
                self.renderer.set_audio_amplitude(amp)
                time.sleep(frame_duration)

            self.renderer.set_audio_amplitude(0.0)

            # Cleanup temp wav
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass

            if on_complete:
                on_complete()

        self.current_audio_thread = threading.Thread(target=worker, daemon=True)
        self.current_audio_thread.start()

    def run(self) -> None:
        """Main execution loop."""
        self.vision.start()
        print("\n" + "=" * 60)
        print("🪄  Harry Potter Talking Portrait (Gemma 4 on Pi 5)")
        print("=" * 60)
        print("Controls:")
        print("  [SPACE]  : Trigger mock person detection (Wake Portrait)")
        print("  [T]      : Inject simulated spoken phrase to STT")
        print("  [ESC/Q]  : Quit")
        print("=" * 60 + "\n")

        last_vision_poll = 0.0
        vision_poll_interval = self.config["vision"].get("poll_interval_seconds", 0.1)

        try:
            while self.running:
                # 1. Process Pygame Events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            self.running = False
                        elif event.key == pygame.K_SPACE:
                            if isinstance(self.vision, MockVision):
                                self.vision.trigger(duration_seconds=3.0)
                        elif event.key == pygame.K_t:
                            if isinstance(self.stt, KeyboardSTT):
                                phrase = self.stt.inject_next_sample()
                                print(f"[Demo] User utterance simulated: \"{phrase}\"")

                # 2. Poll Vision Sensor
                now = time.time()
                if now - last_vision_poll >= vision_poll_interval:
                    detected = self.vision.is_person_detected()
                    self.fsm.on_person_frame(detected)
                    last_vision_poll = now

                # 3. Update State Machine
                self.fsm.update()

                # 4. Render Frame
                self.renderer.render()

        finally:
            self.cleanup()

    def cleanup(self) -> None:
        print("[App] Shutting down Talking Portrait...")
        self.running = False
        self.vision.stop()
        self.renderer.cleanup()


def main():
    args = parse_args()
    app = TalkingPortraitApp(config_path=args.config, demo_mode=args.demo)
    app.run()


if __name__ == "__main__":
    main()
