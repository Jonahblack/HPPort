#!/usr/bin/env python3
"""Harry Potter Talking Portrait - Gemma 4 on Raspberry Pi 5 with Hailo AI HAT.

Main orchestrator integrating:
- Vision: Hailo-8L YOLOv8 / USB camera / Pi Camera Module with live corner PiP feed
- STT: Faster-Whisper / Microphone listener
- LLM: Gemma 4 via local llama.cpp server
- TTS: Piper neural voice with RMS mouth shape lip synchronization
- State Machine: IDLE -> WAKE_PENDING -> GREETING -> LISTENING -> THINKING -> SPEAKING -> COOLDOWN
- Renderer: Pygame 2D layered sprite animation with on-screen HUD & latency profiling
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
        self.is_listening_active = False

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
            self.renderer.set_subtitle("Listening for your voice (or press 'T')...")
            # Spawn worker thread for listening if not already running
            if not self.is_listening_active:
                threading.Thread(target=self._listen_worker, daemon=True).start()

        elif new_state == PortraitState.IDLE:
            self.renderer.set_subtitle("")
            self.renderer.set_audio_amplitude(0.0)

        elif new_state == PortraitState.COOLDOWN:
            self.renderer.set_subtitle("Resting peacefully in the castle corridor...")
            self.renderer.set_audio_amplitude(0.0)

    def _listen_worker(self) -> None:
        """Background worker to listen for user speech."""
        if self.fsm.state != PortraitState.LISTENING:
            return

        self.is_listening_active = True
        stt_start = time.time()
        user_text = self.stt.listen_and_transcribe(timeout_seconds=3.0, max_duration_seconds=10.0)
        stt_duration = time.time() - stt_start
        self.is_listening_active = False

        if user_text and user_text.strip():
            print(f"[STT] User utterance recognized: \"{user_text}\" (took {stt_duration:.2f}s)")
            self.renderer.set_latency_metric("stt", f"{stt_duration:.2f}s")
            self.fsm.on_speech_detected()
            self._generate_and_speak(user_text, stt_duration=stt_duration)
        else:
            self.fsm.on_speech_silence()

    def _generate_and_speak(self, user_text: str, stt_duration: float = 0.0) -> None:
        """Generate LLM response and speak it."""
        self.renderer.set_subtitle("Lord Cadogan is consulting Gemma 4...")

        def worker():
            turn_start = time.time()
            llm_start = time.time()
            reply = self.llm.generate_response(
                user_message=user_text,
                conversation_history=self.conversation_history,
            )
            reply = (reply or "").strip()
            if not reply:
                reply = self.config["llm"].get(
                    "empty_response_text",
                    "The castle spirits stole my answer. Ask once more, brave visitor!",
                )
                print("[Pipeline] Empty LLM response replaced with spoken recovery text.")
            llm_latency = time.time() - llm_start
            self.renderer.set_latency_metric("llm_ttft", f"{llm_latency:.2f}s")
            self.renderer.set_latency_metric("llm_total", f"{llm_latency:.2f}s")

            # Update history
            self.conversation_history.append({"role": "user", "content": user_text})
            self.conversation_history.append({"role": "assistant", "content": reply})

            print(f"[Pipeline] LLM Response: \"{reply}\" ({llm_latency:.2f}s)")
            self.fsm.on_llm_response_ready()
            
            total_turnaround = stt_duration + llm_latency
            self.renderer.set_latency_metric("turnaround", f"{total_turnaround:.2f}s")

            self._speak_phrase(reply, on_complete=self.fsm.on_speaking_complete)

        threading.Thread(target=worker, daemon=True).start()

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

            print(f"[Pipeline] TTS Audio Ready in {synth_latency:.2f}s (Audio length: {duration:.2f}s)")
            tts_engine = getattr(self.tts, "last_engine", "")
            tts_error = getattr(self.tts, "last_error", "")
            if tts_engine == "mock_fallback":
                print(f"[Pipeline] Warning: TTS fallback audio active. {tts_error or 'Piper did not generate speech.'}")
            self.renderer.set_latency_metric("tts", f"{synth_latency:.2f}s")
            self.renderer.set_subtitle(text)

            # Analyze lip sync amplitudes
            amplitudes = self.renderer.lipsync_engine.analyze_wav(out_path, fps=self.renderer.fps)

            # Play audio using pygame.mixer
            try:
                sound = pygame.mixer.Sound(out_path)
                sound.play()
            except Exception as e:
                print(f"[Audio] Pygame sound play notice: {e}")

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
        print("\n" + "=" * 65)
        print("🪄  Harry Potter Talking Portrait (Gemma 4 on Pi 5)")
        print("=" * 65)
        print("Live Controls:")
        print("  [SPACE]  : Trigger mock person detection (Wake Portrait)")
        print("  [T]      : Talk / Inject spoken phrase to STT")
        print("  [C]      : Toggle Corner Live Camera PiP Feed")
        print("  [H]      : Toggle Diagnostic / Latency HUD")
        print("  [ESC/Q]  : Clean Shutdown")
        print("=" * 65 + "\n")

        last_vision_poll = 0.0
        vision_poll_interval = float(self.config["vision"].get("poll_interval_seconds", 0.05))

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
                                self.vision.trigger(duration_seconds=4.0)
                            elif isinstance(self.vision, HailoVision):
                                self.vision.simulate_detection(True)
                                print("[App] Manual person detection triggered via SPACEBAR.")
                        elif event.key == pygame.K_t:
                            # Manually trigger dialogue turn
                            if self.fsm.state in (PortraitState.IDLE, PortraitState.LISTENING, PortraitState.COOLDOWN):
                                sample_utterance = "Greetings Lord Cadogan! What quest awaits us today?"
                                print(f"[App] User utterance injected: \"{sample_utterance}\"")
                                self.fsm.on_speech_detected()
                                self._generate_and_speak(sample_utterance, stt_duration=0.1)
                        elif event.key == pygame.K_c:
                            self.renderer.toggle_camera_pip()
                        elif event.key == pygame.K_h:
                            self.renderer.toggle_debug_hud()

                # 2. Poll Vision Sensor & Update Camera Feed Surface
                now = time.time()
                if now - last_vision_poll >= vision_poll_interval:
                    detected = self.vision.is_person_detected()
                    self.fsm.on_person_frame(detected)
                    
                    # Update live camera frame in renderer
                    cam_frame = self.vision.get_latest_frame()
                    cam_status = self.vision.get_status_info()
                    self.renderer.update_camera_frame(cam_frame, cam_status)
                    
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
