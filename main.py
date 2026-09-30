#!/usr/bin/env python3
"""Raspberry Pi talking portrait: bounded speech pipeline and main-thread state."""

import io
import os
import queue
import tempfile
import threading
import time
import wave

import numpy as np
import pygame

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
from speech_pipeline import SpeechPipelineError, run_speech_pipeline


class TalkingPortraitApp:
    def __init__(self, config_path="portrait_config.json", demo_mode=False, fullscreen=False):
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(config_path)), ".env"))
        self.config = load_config(config_path, demo_mode=demo_mode)
        if fullscreen:
            self.config["renderer"]["fullscreen"] = True
        self.demo_mode = demo_mode
        self.running = True
        self._stop = threading.Event()
        self._events = queue.SimpleQueue()
        self._turn_id = 0
        self._listen_thread = None
        self.current_audio_thread = None
        self._warmup_thread = None
        self.is_listening_active = False
        self.conversation_history = []
        self.fsm = PortraitStateMachine(self.config, on_state_change=self._on_state_change)

        def driver(section, name, real, mock):
            return real(self.config) if not demo_mode and self.config[section].get("driver") == name else mock(self.config)

        self.vision = driver("vision", "hailo", HailoVision, MockVision)
        self.stt = driver("stt", "local_stt", LocalSTT, KeyboardSTT)
        self.llm = driver("llm", "llama_client", LlamaClient, MockLLMClient)
        self.tts = driver("tts", "piper", PiperTTS, MockTTS)
        self.renderer = PortraitRenderer(self.config)
        self.safeguard = TokenSafeguard(self.config)
        self.live_client = GeminiLiveClient(self.config, safeguard=self.safeguard)
        state_config = self.config["state_machine"]
        self.listen_timeout_seconds = float(state_config.get("silence_timeout_seconds", 4.0))
        self.max_listen_duration_seconds = float(state_config.get("max_listen_duration_seconds", 10.0))
        self._update_safeguard_hud()

    def _post(self, callback, *args):
        if self.running:
            self._events.put((callback, args))

    def _drain_events(self):
        # All FSM transitions and their side effects run on the display thread.
        for _ in range(100):
            try:
                callback, args = self._events.get_nowait()
            except queue.Empty:
                break
            if self.running:
                callback(*args)

    def _update_safeguard_hud(self):
        metrics = self.safeguard.get_metrics()
        self.renderer.set_latency_metric("quota", f"{metrics['daily_used']:,}/{metrics['daily_limit']:,} ({metrics['status_text']})")

    def _on_state_change(self, new_state):
        self.renderer.set_state(new_state)
        if new_state == PortraitState.GREETING:
            self._speak_phrase(self.config["llm"]["greeting_prompt"], self.fsm.on_greeting_complete)
        elif new_state == PortraitState.LISTENING:
            self.renderer.set_subtitle("I'm listening...")
            self._ensure_listener()
        elif new_state in (PortraitState.IDLE, PortraitState.COOLDOWN):
            self._turn_id += 1
            self.conversation_history.clear()
            self.renderer.set_subtitle("" if new_state == PortraitState.IDLE else "Until our next adventure...")
            self.renderer.set_viseme("X", amplitude=0.0)
            self.safeguard.reset_session()
            self._update_safeguard_hud()

    def _ensure_listener(self):
        if not self.running or self.is_listening_active or self.fsm.state != PortraitState.LISTENING:
            return
        self.is_listening_active = True
        self._listen_thread = threading.Thread(target=self._listen_worker, args=(self._turn_id,), daemon=True, name="portrait-listen")
        self._listen_thread.start()

    def _listen_worker(self, turn_id):
        started = time.perf_counter()
        text, error = None, None
        try:
            text = self.stt.listen_and_transcribe(self.listen_timeout_seconds, self.max_listen_duration_seconds)
        except Exception as exc:
            error = exc
        self._post(self._on_listen_result, turn_id, text, time.perf_counter() - started, error)

    def _on_listen_result(self, turn_id, text, duration, error):
        self.is_listening_active = False
        if turn_id != self._turn_id or self.fsm.state != PortraitState.LISTENING:
            self._ensure_listener()
            return
        if error:
            self._turn_failed(turn_id, error)
        elif text and text.strip():
            self.renderer.set_latency_metric("stt", f"{duration:.2f}s")
            self._submit_text(text.strip(), duration)
        else:
            self.fsm.on_speech_silence()
            self._ensure_listener()

    def _submit_text(self, text, stt_duration=0.0):
        if self.fsm.state not in (PortraitState.IDLE, PortraitState.COOLDOWN, PortraitState.LISTENING):
            return
        self._turn_id += 1
        self.fsm.on_speech_detected()
        self._generate_and_speak(text, stt_duration)

    def _begin_speaking(self, turn_id):
        if turn_id == self._turn_id:
            self.fsm.on_llm_response_ready()

    def _finish_turn(self, turn_id, user_text, reply):
        if turn_id != self._turn_id:
            return
        if reply:
            self.conversation_history.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}])
            keep = max(0, int(self.config["llm"].get("history_turn_limit", 2))) * 2
            self.conversation_history = self.conversation_history[-keep:] if keep else []
        self.renderer.set_viseme("X", amplitude=0.0)
        self._update_safeguard_hud()
        self.fsm.on_llm_response_ready()
        self.fsm.on_speaking_complete()

    def _turn_failed(self, turn_id, error):
        if turn_id != self._turn_id:
            return
        print(f"[App] Conversation failed: {error}")
        self.fsm.start_cooldown()
        self.renderer.set_subtitle("I lost my train of thought. Please try again in a moment.")

    def _generate_and_speak(self, user_text, stt_duration=0.0):
        turn_id = self._turn_id

        def worker():
            started = time.perf_counter()
            try:
                mode = str(self.config.get("conversation_mode", "auto")).lower()
                available, reason = self.live_client.is_available()
                use_cloud = mode in ("auto", "gemini_live") and available and not self.demo_mode
                reply = None
                if use_cloud:
                    native = self.config["gemini_live"].get("response_voice", "piper") == "native"
                    self.renderer.set_latency_metric("mode", "GEMINI / CHARON" if native else "GEMINI / PIPER")
                    try:
                        reply = (self._execute_gemini_live_turn(user_text, stt_duration, started)
                                 if native else self._execute_pipelined_turn(self.live_client, user_text, started))
                    except SpeechPipelineError as exc:
                        if exc.stage != "generation":
                            raise
                        if exc.spoken:
                            reply = " ".join(exc.spoken)
                        print(f"[App] Gemini stream ended: {exc}")
                    except Exception as exc:
                        print(f"[App] Gemini unavailable: {exc}")
                elif mode != "local" and not self.demo_mode:
                    print(f"[App] Using local model: {reason}")
                if reply is None and not self._stop.is_set():
                    self.renderer.set_latency_metric("mode", "LOCAL / PIPER")
                    reply = self._execute_local_pipelined_turn(user_text, stt_duration, started)
                self._post(self._finish_turn, turn_id, user_text, reply or "")
            except SpeechPipelineError as exc:
                if exc.spoken:
                    self._post(self._finish_turn, turn_id, user_text, " ".join(exc.spoken))
                else:
                    self._post(self._turn_failed, turn_id, exc)
            except Exception as exc:
                self._post(self._turn_failed, turn_id, exc)

        self.current_audio_thread = threading.Thread(target=worker, daemon=True, name="portrait-turn")
        self.current_audio_thread.start()

    def _execute_local_pipelined_turn(self, user_text, stt_duration, turn_start):
        return self._execute_pipelined_turn(self.llm, user_text, turn_start)

    def _execute_pipelined_turn(self, client, user_text, turn_start):
        first_audio = True
        turn_id = self._turn_id

        def clauses():
            first = True
            for text in client.generate_clauses(user_text, conversation_history=list(self.conversation_history)):
                if first:
                    self.renderer.set_latency_metric("llm_ttft", f"{time.perf_counter() - turn_start:.2f}s")
                    first = False
                yield text
            self.renderer.set_latency_metric("llm_total", f"{time.perf_counter() - turn_start:.2f}s")

        def play(prepared):
            nonlocal first_audio
            if first_audio:
                self._post(self._begin_speaking, turn_id)
            self._play_prepared(prepared, turn_start if first_audio else None)
            first_audio = False

        spoken = run_speech_pipeline(clauses(), self._prepare_phrase, play,
                                     self._discard_prepared, self._stop)
        if not spoken and not self._stop.is_set():
            raise RuntimeError("The model returned no spoken response")
        return " ".join(spoken)

    def _prepare_phrase(self, text):
        audio_dir = self.config["hardware"].get("audio_dir")
        if audio_dir:
            try:
                os.makedirs(audio_dir, exist_ok=True)
            except OSError:
                audio_dir = None
        fd, path = tempfile.mkstemp(prefix="portrait_", suffix=".wav", dir=audio_dir)
        os.close(fd)
        try:
            started = time.perf_counter()
            output, duration = self.tts.synthesize_to_file(text, path)
            if os.path.abspath(output) != os.path.abspath(path):
                import shutil
                shutil.copyfile(output, path)
            latency = time.perf_counter() - started
            frames = self.renderer.lipsync_engine.analyze_wav(path, fps=self.renderer.fps)
            return {"text": text, "path": path, "frames": frames, "latency": latency}
        except Exception:
            os.unlink(path)
            raise

    @staticmethod
    def _discard_prepared(prepared):
        try:
            os.unlink(prepared["path"])
        except FileNotFoundError:
            pass

    def _play_prepared(self, prepared, turn_start=None):
        if self._stop.is_set():
            return
        sound = pygame.mixer.Sound(prepared["path"])
        channel = pygame.mixer.Channel(0)
        channel.play(sound)
        started = time.perf_counter()
        if turn_start is not None:
            self.renderer.set_latency_metric("turnaround", f"{started - turn_start:.2f}s")
        self.renderer.set_latency_metric("tts", f"{prepared['latency']:.2f}s")
        self.renderer.set_subtitle(prepared["text"])
        frames = prepared["frames"]
        try:
            while channel.get_busy() and not self._stop.is_set():
                index = int((time.perf_counter() - started) * self.renderer.fps)
                if index < len(frames):
                    frame = frames[index]
                    if isinstance(frame, dict):
                        self.renderer.set_viseme(frame.get("viseme", "X"), amplitude=frame.get("amplitude", 0.0))
                    else:
                        self.renderer.set_audio_amplitude(float(frame))
                self._stop.wait(0.01)
        finally:
            if self._stop.is_set():
                channel.stop()
            self.renderer.set_viseme("X", amplitude=0.0)

    def _execute_gemini_live_turn(self, user_text, stt_duration, turn_start):
        """Receive independently of playback and queue PCM on one mixer channel."""
        chunks = queue.Queue(maxsize=16)
        finished, failed = threading.Event(), threading.Event()
        transcripts, playback_error = [], []
        network_error = None
        received = False
        turn_id = self._turn_id

        def play_stream():
            nonlocal received
            channel = None
            try:
                channel = pygame.mixer.Channel(0)
                while not self._stop.is_set():
                    while channel.get_queue() is not None and not self._stop.is_set():
                        self._stop.wait(0.005)
                    if self._stop.is_set():
                        break
                    try:
                        pcm = chunks.get(timeout=0.01)
                    except queue.Empty:
                        if finished.is_set():
                            break
                        continue
                    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
                    rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0 if samples.size else 0.0
                    wav = io.BytesIO()
                    with wave.open(wav, "wb") as stream:
                        stream.setnchannels(1)
                        stream.setsampwidth(2)
                        stream.setframerate(24000)
                        stream.writeframes(pcm)
                    wav.seek(0)
                    sound = pygame.mixer.Sound(file=wav)
                    if not channel.get_busy():
                        channel.play(sound)
                    else:
                        channel.queue(sound)
                    self.renderer.set_audio_amplitude(min(1.0, rms * 3.0))
                    if not received:
                        received = True
                        latency = time.perf_counter() - turn_start
                        self.renderer.set_latency_metric("turnaround", f"{latency:.2f}s")
                        self._post(self._begin_speaking, turn_id)
                while channel.get_busy() and not self._stop.is_set():
                    self._stop.wait(0.01)
            except Exception as exc:
                playback_error.append(exc)
                failed.set()
            finally:
                if channel and (self._stop.is_set() or failed.is_set()):
                    channel.stop()
                self.renderer.set_viseme("X", amplitude=0.0)

        def on_audio(pcm):
            if not pcm:
                return
            while not self._stop.is_set() and not failed.is_set():
                try:
                    chunks.put(pcm, timeout=0.05)
                    return
                except queue.Full:
                    pass
            raise RuntimeError("Audio playback stopped")

        def on_transcript(role, text):
            if role == "assistant" and text:
                transcripts.append(text)
                self.renderer.set_subtitle("".join(transcripts))

        player = threading.Thread(target=play_stream, daemon=True, name="portrait-live-audio")
        player.start()
        try:
            self.live_client.execute_turn(user_text, on_audio, on_transcript,
                                          conversation_history=list(self.conversation_history))
        except Exception as exc:
            network_error = exc
        finally:
            finished.set()
            while player.is_alive() and not self._stop.is_set():
                player.join(timeout=0.1)
        if playback_error and not received:
            raise playback_error[0]
        if network_error and not received:
            raise network_error
        # Never repeat a partially audible response through the fallback model.
        return "".join(transcripts).strip() if received else None

    def _speak_phrase_blocking(self, text):
        prepared = self._prepare_phrase(text)
        try:
            self._play_prepared(prepared)
        finally:
            self._discard_prepared(prepared)

    def _speak_phrase(self, text, on_complete=None):
        turn_id = self._turn_id

        def worker():
            try:
                self._speak_phrase_blocking(text)
                if on_complete:
                    self._post(on_complete)
            except Exception as exc:
                self._post(self._turn_failed, turn_id, exc)

        self.current_audio_thread = threading.Thread(target=worker, daemon=True, name="portrait-greeting")
        self.current_audio_thread.start()

    def run(self):
        last_vision_poll = 0.0
        interval = max(0.02, float(self.config["vision"].get("poll_interval_seconds", 0.1)))
        print("[App] SPACE: wake | T: test question | C: camera | H: diagnostics | ESC/Q: quit")
        try:
            self.vision.start()
            if hasattr(self.tts, "warmup") and self.config["tts"].get("warmup_enabled", True):
                def warmup():
                    try:
                        self.tts.warmup(self.config["llm"]["greeting_prompt"])
                    except Exception as exc:
                        print(f"[TTS] Warmup notice: {exc}")
                self._warmup_thread = threading.Thread(target=warmup, daemon=True, name="portrait-warmup")
                self._warmup_thread.start()
            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_ESCAPE, pygame.K_q):
                            self.running = False
                        elif event.key == pygame.K_SPACE:
                            if isinstance(self.vision, MockVision):
                                self.vision.trigger(duration_seconds=4.0)
                            else:
                                self.vision.simulate_detection(True)
                        elif event.key == pygame.K_t:
                            self._submit_text("Greetings Wilhelm! What quest awaits us today?")
                        elif event.key == pygame.K_c:
                            self.renderer.toggle_camera_pip()
                        elif event.key == pygame.K_h:
                            self.renderer.toggle_debug_hud()
                if not self.running:
                    break
                self._drain_events()
                now = time.monotonic()
                if now - last_vision_poll >= interval:
                    self.fsm.on_person_frame(self.vision.is_person_detected())
                    gaze_x, gaze_y, distance = self.vision.get_visitor_gaze()
                    self.renderer.set_gaze_target(gaze_x, gaze_y, distance=distance)
                    frame = self.vision.get_latest_frame(target_size=(200, 150)) if self.renderer.show_camera_pip else None
                    self.renderer.update_camera_frame(frame, self.vision.get_status_info())
                    last_vision_poll = now
                self.fsm.update()
                self.renderer.render()
        finally:
            self.cleanup()

    def cleanup(self):
        self.running = False
        self._stop.set()
        if pygame.mixer.get_init():
            pygame.mixer.stop()
        self.vision.stop()
        for thread in (self.current_audio_thread, self._listen_thread, self._warmup_thread):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=1.0)
        for component in (self.stt, self.llm, self.live_client, self.tts):
            close = getattr(component, "close", None)
            if close:
                close()
        self.renderer.cleanup()


def main():
    args = parse_args()
    app = TalkingPortraitApp(args.config, demo_mode=args.demo, fullscreen=args.fullscreen)
    app.run()


if __name__ == "__main__":
    main()
