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
import io
import array
import math
import wave
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
from live.safeguard import TokenSafeguard
from live.gemini_live import GeminiLiveClient


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

        # Initialize Token Safeguard & Gemini Live Client
        self.safeguard = TokenSafeguard(self.config)
        self.live_client = GeminiLiveClient(self.config, safeguard=self.safeguard)

        # Runtime control variables
        self.running = True
        self.conversation_history = []
        self.current_audio_thread: Optional[threading.Thread] = None
        self.is_listening_active = False
        state_config = self.config.get("state_machine", {})
        self.listen_timeout_seconds = float(state_config.get("silence_timeout_seconds", 1.2))
        self.max_listen_duration_seconds = float(state_config.get("max_listen_duration_seconds", 5.0))

        self._update_safeguard_hud()

    def _update_safeguard_hud(self) -> None:
        """Publish active mode and token quota information to the HUD."""
        metrics = self.safeguard.get_metrics()
        quota_text = f"{metrics['daily_used']:,}/{metrics['daily_limit']:,} ({metrics['status_text']})"
        self.renderer.set_latency_metric("quota", quota_text)

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
            self.renderer.set_viseme("X", amplitude=0.0)
            self.safeguard.reset_session()
            self._update_safeguard_hud()

        elif new_state == PortraitState.COOLDOWN:
            self.renderer.set_subtitle("Resting peacefully in the castle corridor...")
            self.renderer.set_audio_amplitude(0.0)
            self.renderer.set_viseme("X", amplitude=0.0)
            self.safeguard.reset_session()
            self._update_safeguard_hud()

    def _listen_worker(self) -> None:
        """Keep opening capture windows until speech arrives or the FSM leaves LISTENING."""
        if self.fsm.state != PortraitState.LISTENING:
            return

        self.is_listening_active = True
        try:
            while self.running and self.fsm.state == PortraitState.LISTENING:
                stt_start = time.time()
                user_text = self.stt.listen_and_transcribe(
                    timeout_seconds=self.listen_timeout_seconds,
                    max_duration_seconds=self.max_listen_duration_seconds,
                )
                stt_duration = time.time() - stt_start

                # A keyboard-injected turn may have changed state while capture was blocked.
                if not self.running or self.fsm.state != PortraitState.LISTENING:
                    if user_text:
                        print("[STT] Discarding microphone result because another turn is already active.")
                    return

                if user_text and user_text.strip():
                    print(f"[STT] User utterance recognized: \"{user_text}\" (took {stt_duration:.2f}s)")
                    self.renderer.set_latency_metric("stt", f"{stt_duration:.2f}s")
                    self.fsm.on_speech_detected()
                    self._generate_and_speak(user_text, stt_duration=stt_duration)
                    return

                self.fsm.on_speech_silence()
                if self.fsm.state == PortraitState.LISTENING:
                    self.renderer.set_subtitle("Still listening... speak toward the USB microphone.")
                    print("[STT] Reopening microphone capture window.")
        finally:
            self.is_listening_active = False

    def _play_pcm_chunk(self, pcm_bytes: bytes, sample_rate: int = 24000) -> None:
        """Play raw PCM chunk in Pygame and animate mouth shape."""
        if not pcm_bytes:
            return

        # Compute RMS for mouth flap
        samples = array.array("h", pcm_bytes)
        if len(samples) > 0:
            sum_sq = sum(s * s for s in samples)
            rms = (math.sqrt(sum_sq / len(samples))) / 32768.0
            self.renderer.set_audio_amplitude(min(1.0, rms * 3.0))

        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        wav_buf.seek(0)

        try:
            sound = pygame.mixer.Sound(wav_buf)
            sound.play()
            duration = len(samples) / float(sample_rate)
            time.sleep(max(0.01, duration * 0.9))
        except Exception as e:
            print(f"[Audio] PCM chunk playback error: {e}")

    def _execute_gemini_live_turn(self, user_text: str, stt_duration: float, turn_start: float) -> bool:
        """Execute real-time conversational turn via Gemini Live API."""
        llm_start = time.time()
        first_chunk_received = False
        assistant_transcripts = []

        def on_audio_chunk(pcm_24k_bytes: bytes):
            nonlocal first_chunk_received
            if not first_chunk_received:
                first_chunk_received = True
                ttft = time.time() - llm_start
                self.renderer.set_latency_metric("llm_ttft", f"{ttft:.2f}s")
                self.renderer.set_latency_metric("turnaround", f"{(stt_duration + ttft):.2f}s")
                self.fsm.on_llm_response_ready()

            self._play_pcm_chunk(pcm_24k_bytes, sample_rate=24000)

        def on_transcript(role: str, text: str):
            if role == "assistant" and text:
                assistant_transcripts.append(text)
                self.renderer.set_subtitle(" ".join(assistant_transcripts))

        success = self.live_client.execute_turn(
            user_input=user_text,
            on_audio_chunk=on_audio_chunk,
            on_transcript=on_transcript,
        )

        if success:
            full_reply = " ".join(assistant_transcripts).strip() or "By my troth, a bold query!"
            self.conversation_history.append({"role": "user", "content": user_text})
            self.conversation_history.append({"role": "assistant", "content": full_reply})
            self.renderer.set_audio_amplitude(0.0)
            self.renderer.set_viseme("X", amplitude=0.0)
            self.fsm.on_speaking_complete()
            return True

        return False

    def _execute_local_pipelined_turn(self, user_text: str, stt_duration: float, turn_start: float) -> None:
        """Stream clauses from local LLM and pipeline into Piper TTS."""
        llm_start = time.time()
        first_clause_spoken = False
        full_reply_clauses = []

        for clause in self.llm.generate_clauses(
            user_message=user_text,
            conversation_history=self.conversation_history,
        ):
            clause = (clause or "").strip()
            if not clause:
                continue

            if not first_clause_spoken:
                ttft = time.time() - llm_start
                self.renderer.set_latency_metric("llm_ttft", f"{ttft:.2f}s")
                self.renderer.set_latency_metric("turnaround", f"{(stt_duration + ttft):.2f}s")
                self.fsm.on_llm_response_ready()
                first_clause_spoken = True

            full_reply_clauses.append(clause)
            self._speak_phrase_blocking(clause)

        llm_total = time.time() - llm_start
        self.renderer.set_latency_metric("llm_total", f"{llm_total:.2f}s")

        full_reply = " ".join(full_reply_clauses).strip()
        if not full_reply:
            full_reply = self.config["llm"].get(
                "empty_response_text",
                "The castle spirits stole my answer. Ask once more, brave visitor!",
            )
            self._speak_phrase_blocking(full_reply)

        self.conversation_history.append({"role": "user", "content": user_text})
        self.conversation_history.append({"role": "assistant", "content": full_reply})
        self.renderer.set_audio_amplitude(0.0)
        self.renderer.set_viseme("X", amplitude=0.0)
        self.fsm.on_speaking_complete()

    def _generate_and_speak(self, user_text: str, stt_duration: float = 0.0) -> None:
        """Generate response via Gemini Live (if online & under quota) or local pipelined stream."""
        def worker():
            turn_start = time.time()
            conv_mode = str(self.config.get("conversation_mode", "auto")).lower()
            can_use_live, live_reason = self.live_client.is_available()
            use_live = (conv_mode in ("auto", "gemini_live")) and can_use_live and not self.demo_mode

            self._update_safeguard_hud()

            if use_live:
                self.renderer.set_subtitle("Lord Cadogan is consulting Gemini Live...")
                self.renderer.set_latency_metric("mode", "GEMINI LIVE")
                success = self._execute_gemini_live_turn(user_text, stt_duration, turn_start)
                self._update_safeguard_hud()
                if success:
                    return

                # If Gemini Live failed (quota reached or network lost), report and fall back to local
                can_use_after, reason_after = self.safeguard.can_use_live_api()
                if not can_use_after:
                    fallback_text = self.safeguard.fallback_speech
                    print(f"[Safeguard] Quota limit reached: {reason_after}. Switching to local.")
                    self._speak_phrase_blocking(fallback_text)
                    self._update_safeguard_hud()

            # Local Pipelined Streaming Fallback / Default
            self.renderer.set_subtitle("Lord Cadogan is consulting local enchantments...")
            self.renderer.set_latency_metric("mode", "LOCAL OFFLINE")
            self._execute_local_pipelined_turn(user_text, stt_duration, turn_start)
            self._update_safeguard_hud()

        self.current_audio_thread = threading.Thread(target=worker, daemon=True)
        self.current_audio_thread.start()

    def _speak_phrase_blocking(self, text: str) -> None:
        """Synthesize audio and play with mouth synchronization synchronously."""
        cache_dir = self.config.get("hardware", {}).get("cache_dir", "/mnt/portrait/cache")
        audio_dir = self.config.get("hardware", {}).get("audio_dir", cache_dir)
        if not os.path.exists(audio_dir):
            audio_dir = "/tmp"

        wav_path = os.path.join(audio_dir, f"clause_{int(time.time()*1000)}.wav")

        synth_start = time.time()
        out_path, duration = self.tts.synthesize_to_file(text, wav_path)
        synth_latency = time.time() - synth_start

        self.renderer.set_latency_metric("tts", f"{synth_latency:.2f}s")
        self.renderer.set_subtitle(text)

        viseme_frames = self.renderer.lipsync_engine.analyze_wav(out_path, fps=self.renderer.fps)

        try:
            sound = pygame.mixer.Sound(out_path)
            sound.play()
        except Exception as e:
            print(f"[Audio] Pygame sound play notice: {e}")

        frame_duration = 1.0 / self.renderer.fps
        for frame_info in viseme_frames:
            if not self.running or self.fsm.state not in (PortraitState.GREETING, PortraitState.SPEAKING):
                break
            if isinstance(frame_info, dict):
                amp = frame_info.get("amplitude", 0.0)
                viseme = frame_info.get("viseme", "X")
                self.renderer.set_viseme(viseme, amplitude=amp)
            else:
                self.renderer.set_audio_amplitude(float(frame_info))
            time.sleep(frame_duration)

        self.renderer.set_viseme("X", amplitude=0.0)
        self.renderer.set_audio_amplitude(0.0)

        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass

    def _speak_phrase(self, text: str, on_complete: Optional[callable] = None) -> None:
        """Asynchronously synthesize audio and play with mouth synchronization."""
        def worker():
            self._speak_phrase_blocking(text)
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
                                sample_utterance = "Greetings Wilhelm! What quest awaits us today?"
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

                    # Update visitor gaze tracking from camera/Hailo
                    if hasattr(self.vision, "get_visitor_gaze"):
                        gaze_x, gaze_y, dist = self.vision.get_visitor_gaze()
                        self.renderer.set_gaze_target(gaze_x, gaze_y, distance=dist)

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
