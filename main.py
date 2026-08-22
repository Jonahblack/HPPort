#!/usr/bin/env python3
"""
Harry Potter Talking Portrait - Main Application.
Runs an interactive, Gemma 4 E2B powered talking portrait on Raspberry Pi 5 / Desktop PC.
"""

import argparse
import logging
import os
import queue
import sys
import threading
import time
from typing import Dict, List, Optional

from config import AppConfig, load_config
from llm.base import BaseLLMClient, LLMResponse
from llm.llama_client import LlamaClient
from llm.mock_client import MockLLMClient
from renderer.animation import AnimationController
from renderer.renderer import PortraitRenderer
from state_machine import State, StateMachine
from stt.base import BaseSTT, STTResult
from stt.keyboard_stt import KeyboardSTT
from stt.local_stt import LocalSTT
from tts.base import BaseTTS, TTSAudioResult
from tts.mock_tts import MockTTS
from tts.piper import PiperTTS
from vision.base import BaseVisionDetector, DetectionFrame
from vision.hailo import HailoVision
from vision.mock import MockVision

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TalkingPortrait")


class TalkingPortraitApp:
    """Core controller coordinating State Machine, Vision, STT, Gemma LLM, Piper TTS, and Renderer."""

    def __init__(self, config: AppConfig, demo_mode: bool = False):
        self.config = config
        self.demo_mode = demo_mode
        self.running = False

        # Instrumentation / Latency stats
        self.latency_metrics: Dict[str, str] = {}
        self.conversation_history: List[Dict[str, str]] = []

        # 1. State Machine
        self.fsm = StateMachine(
            wake_confirm_frames=config.state_machine.wake_confirm_frames,
            wake_confirm_timeout_seconds=config.state_machine.wake_confirm_timeout_seconds,
            cooldown_duration_seconds=config.state_machine.cooldown_duration_seconds,
            max_silence_turns=config.state_machine.max_consecutive_silence,
        )

        # 2. Vision Detector
        if config.vision.driver == "mock" or demo_mode:
            self.vision: BaseVisionDetector = MockVision(poll_interval_seconds=config.vision.poll_interval_seconds)
        else:
            self.vision = HailoVision(
                confidence_threshold=config.vision.confidence_threshold,
                poll_interval_seconds=config.vision.poll_interval_seconds,
                camera_width=config.vision.camera_width,
                camera_height=config.vision.camera_height,
            )

        # 3. LLM Client (Gemma 4 E2B Instruct via llama.cpp)
        if config.llm.driver == "mock_client" or demo_mode:
            self.llm: BaseLLMClient = MockLLMClient(system_prompt=config.llm.system_prompt)
        else:
            self.llm = LlamaClient(
                endpoint_url=config.llm.endpoint_url,
                model_name=config.llm.model_name,
                system_prompt=config.llm.system_prompt,
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
            )

        # 4. Speech to Text (STT)
        if config.stt.driver == "keyboard_stt" or demo_mode:
            self.stt: BaseSTT = KeyboardSTT()
        else:
            self.stt = LocalSTT(
                model_size=config.stt.model_size,
                language=config.stt.language,
                device=config.stt.device,
                compute_type=config.stt.compute_type,
                energy_threshold=config.stt.energy_threshold,
                silence_timeout_seconds=config.state_machine.silence_timeout_seconds,
                max_duration_seconds=config.state_machine.max_listen_duration_seconds,
            )

        # 5. Text to Speech (Piper TTS)
        if config.tts.driver == "mock_tts" or demo_mode:
            self.tts: BaseTTS = MockTTS()
        else:
            self.tts = PiperTTS(
                piper_binary_path=config.tts.piper_binary_path,
                model_path=config.tts.model_path,
                model_config_path=config.tts.model_config_path,
                speaker_id=config.tts.speaker_id,
                length_scale=config.tts.length_scale,
            )

        # 6. Animator & Pygame Renderer
        self.animator = AnimationController(
            blink_min_seconds=config.renderer.blink_min_seconds,
            blink_max_seconds=config.renderer.blink_max_seconds,
            threshold_mouth_2=config.renderer.amplitude_threshold_mouth_2,
            threshold_mouth_3=config.renderer.amplitude_threshold_mouth_3,
        )
        self.renderer = PortraitRenderer(
            width=config.renderer.width,
            height=config.renderer.height,
            fullscreen=config.renderer.fullscreen,
            fps=config.renderer.fps,
            assets_dir=config.renderer.assets_dir,
            animator=self.animator,
        )

        # Work Queues for asynchronous processing
        self._action_queue: queue.Queue = queue.Queue()
        self._status_text: str = "Awaiting visitor..."

        self._setup_fsm_callbacks()

    def _setup_fsm_callbacks(self) -> None:
        """Connect state machine lifecycle transitions to actions."""
        self.fsm.register_on_enter(State.IDLE, self._on_enter_idle)
        self.fsm.register_on_enter(State.WAKE_PENDING, self._on_enter_wake_pending)
        self.fsm.register_on_enter(State.GREETING, self._on_enter_greeting)
        self.fsm.register_on_enter(State.LISTENING, self._on_enter_listening)
        self.fsm.register_on_enter(State.THINKING, self._on_enter_thinking)
        self.fsm.register_on_enter(State.SPEAKING, self._on_enter_speaking)
        self.fsm.register_on_enter(State.COOLDOWN, self._on_enter_cooldown)

    def _on_enter_idle(self, prev_state: State) -> None:
        self._status_text = "Idle - Watching for visitor"
        self.conversation_history.clear()
        self.animator.set_audio_amplitude(0.0)

    def _on_enter_wake_pending(self, prev_state: State) -> None:
        self._status_text = "Confirming visitor presence..."

    def _on_enter_greeting(self, prev_state: State) -> None:
        self._status_text = "Delivering grand greeting..."
        greeting_text = self.config.llm.greeting_prompt
        threading.Thread(target=self._speak_dialogue_worker, args=(greeting_text, self.fsm.on_greeting_finished), daemon=True).start()

    def _on_enter_listening(self, prev_state: State) -> None:
        self._status_text = "Listening for your voice..."
        self.animator.set_audio_amplitude(0.0)
        self.stt.start_listening(
            callback=self._handle_stt_result,
            on_silence=self.fsm.on_silence_timeout,
        )

    def _on_enter_thinking(self, prev_state: State) -> None:
        self._status_text = "Lord Cadogan is consulting Gemma 4..."

    def _on_enter_speaking(self, prev_state: State) -> None:
        self._status_text = "Speaking..."

    def _on_enter_cooldown(self, prev_state: State) -> None:
        self._status_text = f"Resting in portrait cooldown ({self.config.state_machine.cooldown_duration_seconds}s)..."
        self.stt.stop_listening()
        self.animator.set_audio_amplitude(0.0)

    def _handle_vision_frame(self, frame: DetectionFrame) -> None:
        if frame.person_detected and frame.confidence >= self.config.vision.confidence_threshold:
            self.fsm.on_person_detected()

    def _handle_stt_result(self, result: STTResult) -> None:
        logger.info("Visitor spoke: '%s' (STT duration: %.2fs)", result.text, result.duration_seconds)
        self.stt.stop_listening()

        # Check for explicit farewell words
        lower_txt = result.text.lower()
        if any(w in lower_txt for w in ("goodbye", "farewell", "bye", "leave")):
            self.fsm.on_conversation_ended(reason="Visitor bid farewell")
            return

        self.fsm.on_speech_received(result.text)
        threading.Thread(target=self._llm_thinking_worker, args=(result.text, result.duration_seconds), daemon=True).start()

    def _llm_thinking_worker(self, user_prompt: str, stt_duration: float) -> None:
        """Generate response via Gemma 4 and stream to Piper TTS with latency profiling."""
        start_turn_time = time.time()
        self.conversation_history.append({"role": "user", "content": user_prompt})

        # Query Gemma
        llm_resp: LLMResponse = self.llm.generate(user_prompt, self.conversation_history)
        self.conversation_history.append({"role": "assistant", "content": llm_resp.text})

        # Synthesize Piper audio
        tts_start = time.time()
        audio_res: TTSAudioResult = self.tts.synthesize(llm_resp.text)
        tts_gen_time = time.time() - tts_start

        total_turn_latency = (time.time() - start_turn_time) + stt_duration

        # Format Latency Benchmark Instrumentation
        self.latency_metrics = {
            "STT": f"{stt_duration:.2f} s",
            "Gemma TTFT": f"{llm_resp.metrics.time_to_first_token_seconds:.2f} s",
            "Gemma Rate": f"{llm_resp.metrics.tokens_per_second:.1f} tok/s",
            "TTS Gen": f"{tts_gen_time:.2f} s",
            "Turn Latency": f"{total_turn_latency:.2f} s",
        }

        logger.info("=== TURN LATENCY BREAKDOWN ===")
        logger.info("STT:                 %.2f s", stt_duration)
        logger.info("LLM first token:     %.2f s", llm_resp.metrics.time_to_first_token_seconds)
        logger.info("LLM generation:      %.1f tok/s", llm_resp.metrics.tokens_per_second)
        logger.info("TTS first audio:     %.2f s", audio_res.metrics.time_to_first_audio_seconds if audio_res.metrics else 0.0)
        logger.info("Total turn-around:   %.2f s", total_turn_latency)
        logger.info("==============================")

        self.fsm.on_llm_response_ready()
        self._play_tts_and_animate(audio_res, on_finished=self.fsm.on_speech_playback_finished)

    def _speak_dialogue_worker(self, text: str, on_finished: Optional[callable] = None) -> None:
        audio_res = self.tts.synthesize(text)
        self._play_tts_and_animate(audio_res, on_finished=on_finished)

    def _play_tts_and_animate(self, audio_res: TTSAudioResult, on_finished: Optional[callable] = None) -> None:
        def amp_callback(level: float):
            self.animator.set_audio_amplitude(level)

        self.tts.play_audio(
            audio_result=audio_res,
            amplitude_callback=amp_callback,
            on_finished=on_finished,
        )

    def run(self) -> None:
        """Main application execution loop."""
        logger.info("Starting Talking Portrait Application (Target: %s)...", self.config.hardware.target)
        self.running = True

        # Initialize Pygame Renderer
        if not self.renderer.init_display():
            logger.error("Could not initialize renderer. Exiting.")
            return

        # Start Vision detector
        self.vision.start(self._handle_vision_frame)

        # Health check LLM backend
        if not self.llm.health_check():
            logger.warning("Gemma LLM server at %s is currently unreachable.", getattr(self.llm, "endpoint_url", "mock"))

        def on_space():
            logger.info("Spacebar pressed: Simulating visitor arrival.")
            if isinstance(self.vision, MockVision):
                self.vision.trigger_visitor()
            else:
                self.fsm.on_person_detected()

        def on_text_injected(txt: str):
            if isinstance(self.stt, KeyboardSTT):
                self.stt.inject_text(txt)
            else:
                self._handle_stt_result(STTResult(text=txt, duration_seconds=0.1))

        def on_quit():
            self.running = False

        try:
            while self.running and self.renderer.running:
                # 1. Process Pygame window & keyboard events
                self.renderer.handle_events(
                    on_space_pressed=on_space,
                    on_quit=on_quit,
                    on_text_injected=on_text_injected,
                )

                # 2. Update FSM timers (timeouts, cooldown countdowns)
                self.fsm.update()

                # 3. Render next frame
                self.renderer.render(
                    state=self.fsm.state,
                    status_text=self._status_text,
                    latency_metrics=self.latency_metrics if self.config.logging.latency_profiling else None,
                )

                time.sleep(0.001)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received.")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Clean resource shutdown."""
        logger.info("Shutting down Talking Portrait subsystems...")
        self.running = False
        self.vision.stop()
        self.stt.stop_listening()
        self.tts.stop_playback()
        self.renderer.close()
        logger.info("Shutdown complete.")


def main():
    parser = argparse.ArgumentParser(description="Harry Potter Talking Portrait (Gemma 4 / Pi 5)")
    parser.add_argument("--demo", action="store_true", help="Run in Desktop Demo Mode (Mock Vision/STT/TTS/LLM)")
    parser.add_argument("--config", type=str, default="portrait_config.json", help="Path to config JSON")
    parser.add_argument("--fullscreen", action="store_true", help="Force fullscreen display")
    args = parser.parse_args()

    config = load_config(args.config, demo_mode=args.demo)
    if args.fullscreen:
        config.renderer.fullscreen = True

    app = TalkingPortraitApp(config=config, demo_mode=args.demo)
    app.run()


if __name__ == "__main__":
    main()
