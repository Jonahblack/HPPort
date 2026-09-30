"""Pygame cinematic character renderer with animated frames and corner camera PiP feed."""

import os
import time
import math
import random
from collections import OrderedDict
import pygame
from typing import Dict, Any, Optional, Tuple
from state_machine import PortraitState
from renderer.animation import BlinkController, LipSyncEngine, SaccadeController, VISEME_NAMES


class PortraitRenderer:
    """Render full character frames or legacy layers, followed by subtitles, camera PiP, and HUD."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("renderer", {})
        self.audio_config = config.get("tts", {})
        self.width = int(self.config.get("width", 1024))
        self.height = int(self.config.get("height", 768))
        self.fullscreen = bool(self.config.get("fullscreen", False))
        self.fps = max(1, int(self.config.get("fps", 30)))
        self.assets_dir = self.config.get("assets_dir", "assets")
        self.asset_mode = str(self.config.get("asset_mode", "layered")).strip().lower()
        self.camera_motion = bool(self.config.get("camera_motion", True))
        self.ambient_motes = bool(self.config.get("ambient_motes", True))

        # Gaze tracking and interactive presence settings
        self.gaze_tracking_enabled = bool(self.config.get("gaze_tracking_enabled", True))
        self.gaze_sensitivity_x = float(self.config.get("gaze_sensitivity_x", 1.0))
        self.gaze_sensitivity_y = float(self.config.get("gaze_sensitivity_y", 0.8))
        self.viseme_crossfade = bool(self.config.get("viseme_crossfade", True))

        audio_driver = str(self.audio_config.get("audio_driver", "auto")).strip().lower()
        if audio_driver and audio_driver != "auto" and "SDL_AUDIODRIVER" not in os.environ:
            os.environ["SDL_AUDIODRIVER"] = audio_driver

        mixer_rate = int(self.audio_config.get("playback_sample_rate", 22050))
        mixer_channels = int(self.audio_config.get("playback_channels", 1))
        mixer_buffer = int(self.audio_config.get("playback_buffer_size", 512))

        pygame.mixer.pre_init(frequency=mixer_rate, size=-16, channels=mixer_channels, buffer=mixer_buffer)
        pygame.init()
        pygame.font.init()
        try:
            pygame.mixer.init()
            print(
                f"[Audio] Pygame mixer initialized "
                f"({mixer_rate}Hz, channels={mixer_channels}, buffer={mixer_buffer})."
            )
        except Exception as exc:
            print(f"[Audio] Pygame mixer initialization notice: {exc}")

        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        pygame.display.set_caption(self.config.get("window_title", "Harry Potter Talking Portrait (Gemma 4)"))

        self.clock = pygame.time.Clock()
        
        # Load System Fonts
        self.font = pygame.font.SysFont("Georgia", 20, italic=True)
        self.hud_font = pygame.font.SysFont("Courier New", 13, bold=True)
        self.badge_font = pygame.font.SysFont("Georgia", 14, bold=True)
        self._text_cache = OrderedDict()
        self._subtitle_cache_key = None
        self._subtitle_surface = None
        self._mote_sprites = {}
        self._viewport_size = (self.width, self.height)
        self._camera_preview_source = None
        self._camera_preview = None

        # Animation controllers
        self.blink_controller = BlinkController(
            min_interval_sec=float(self.config.get("blink_min_seconds", 2.2)),
            max_interval_sec=float(self.config.get("blink_max_seconds", 5.5)),
            blink_duration_ms=int(self.config.get("blink_duration_ms", 180)),
        )
        self.lipsync_engine = LipSyncEngine(
            threshold_mouth_2=float(self.config.get("amplitude_threshold_mouth_2", 0.15)),
            threshold_mouth_3=float(self.config.get("amplitude_threshold_mouth_3", 0.45)),
            crossfade_ms=int(self.config.get("viseme_crossfade_duration_ms", 35)),
        )
        self.saccade_controller = SaccadeController(
            min_interval=1.2,
            max_interval=3.0,
            max_jitter_px=2.0,
        )

        # Sprites dictionary
        self.sprites: Dict[str, Optional[pygame.Surface]] = {}
        self._scaled_sprite_cache: Dict[Tuple[str, int, int], pygame.Surface] = {}
        self._load_sprites()

        particle_rng = random.Random(1492)
        self.magic_motes = [
            (
                particle_rng.random(),
                particle_rng.random(),
                particle_rng.uniform(0.035, 0.085),
                particle_rng.uniform(0.8, 2.2),
                particle_rng.uniform(0.0, math.tau),
            )
            for _ in range(18)
        ]

        # State and animation variables
        self.current_state = PortraitState.IDLE
        self.current_mouth_index = 1
        self.current_viseme = "X"
        self.previous_viseme = "X"
        self.audio_amplitude = 0.0
        self.subtitle_text = ""
        self.show_debug_hud = bool(self.config.get("show_debug_hud", False))
        self.show_camera_pip = bool(self.config.get("show_camera_pip", False))
        self.camera_feed_surface: Optional[pygame.Surface] = None
        self.camera_status_info: Dict[str, Any] = {}

        # Gaze tracking targets and filtered positions
        self.target_gaze_x = 0.0
        self.target_gaze_y = 0.0
        self.current_gaze_x = 0.0
        self.current_gaze_y = 0.0
        self.target_distance = 1.0
        self.current_distance = 1.0

        # Latency instrumentation
        self.latency_metrics: Dict[str, str] = {
            "stt": "--",
            "llm_ttft": "--",
            "llm_total": "--",
            "tts": "--",
            "turnaround": "--",
        }

        # Idle motion physics
        self.anim_time = 0.0
        self._last_render_time = time.monotonic()
        self.eye_offset_x = 0.0
        self.eye_offset_y = 0.0

    def _load_sprites(self) -> None:
        """Load sprite image layers from assets directory with fallback naming support."""
        if self.asset_mode == "full_frames":
            filenames = {
                "background": ["background.png", "castle_background.png", "bg.png"],
                "torso": ["torso.png", "body.png"],
                "base": ["forest_warrior_neutral.png", "base.png"],
                "eyes_half": ["forest_warrior_blink_half.png", "eyes_half.png"],
                "eyes_closed": ["forest_warrior_blink.png", "eyes_closed.png"],
                "mouth_1": ["forest_warrior_neutral.png", "mouth_1.png"],
                "mouth_2": ["forest_warrior_mouth_2.png", "mouth_2.png"],
                "mouth_3": ["forest_warrior_mouth_3.png", "mouth_3.png"],
            }
        else:
            filenames = {
                "background": ["background.png", "castle_background.png", "bg.png"],
                "torso": ["torso.png", "body.png"],
                "base": ["base.png", "wilhelm_base.png", "cadogan_base.png"],
                "eyes_half": ["eyes_half.png", "wilhelm_eyes_half.png", "cadogan_eyes_half.png"],
                "eyes_closed": ["eyes_closed.png", "wilhelm_eyes_closed.png", "cadogan_eyes_closed.png"],
                "mouth_1": ["mouth_1.png", "wilhelm_mouth_1.png", "cadogan_mouth_1.png"],
                "mouth_2": ["mouth_2.png", "wilhelm_mouth_2.png", "cadogan_mouth_2.png"],
                "mouth_3": ["mouth_3.png", "wilhelm_mouth_3.png", "cadogan_mouth_3.png"],
            }

        # Add Preston-Blair visemes
        for v in VISEME_NAMES:
            filenames[f"viseme_{v}"] = [
                f"viseme_{v.lower()}.png",
                f"wilhelm_viseme_{v.lower()}.png",
                f"cadogan_viseme_{v.lower()}.png",
                f"mouth_{v}.png",
            ]

        configured_files = self.config.get("sprite_files", {})
        if isinstance(configured_files, dict):
            for key, filename in configured_files.items():
                if key in filenames and isinstance(filename, str) and filename:
                    filenames[key].insert(0, filename)

        loaded_paths = {}
        for key, candidates in filenames.items():
            loaded = False
            for fname in candidates:
                path = os.path.join(self.assets_dir, fname)
                if os.path.exists(path):
                    try:
                        img = loaded_paths.get(path)
                        if img is None:
                            img = pygame.image.load(path)
                            # Full-frame paintings are opaque; avoid alpha blending the
                            # entire canvas on every Pi display refresh.
                            img = img.convert() if self.asset_mode == "full_frames" else img.convert_alpha()
                            loaded_paths[path] = img
                        self.sprites[key] = img
                        print(f"[Renderer] Loaded sprite layer '{key}': {path}")
                        loaded = True
                        break
                    except Exception as e:
                        print(f"[Renderer] Failed to load {path}: {e}")
            if not loaded:
                self.sprites[key] = None

    def _scaled_sprite(self, key: str, sprite: pygame.Surface, size: Tuple[int, int]) -> pygame.Surface:
        cache_key = (key, size[0], size[1])
        cached = self._scaled_sprite_cache.get(cache_key)
        if cached is None:
            cached = pygame.transform.smoothscale(sprite, size)
            self._scaled_sprite_cache[cache_key] = cached
        return cached

    def _text(self, font, text: str, color: Tuple[int, int, int]) -> pygame.Surface:
        """Keep unchanged labels cheap without retaining every debug value forever."""
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is None:
            cached = font.render(text, True, color)
            self._text_cache[key] = cached
            if len(self._text_cache) > 128:
                self._text_cache.popitem(last=False)
        else:
            self._text_cache.move_to_end(key)
        return cached

    def _get_subtitle_surface(self, max_width: int, max_height: int) -> pygame.Surface:
        """Wrap captions once per utterance or resize, with a translucent backdrop."""
        max_width = max(40, max_width)
        key = (self.subtitle_text, max_width, max_height)
        if key == self._subtitle_cache_key:
            return self._subtitle_surface

        text_width = max_width - 28
        line_height = self.font.get_linesize()
        max_lines = max(1, (max_height - 20) // line_height)
        lines = []
        line = ""
        for word in self.subtitle_text.split():
            candidate = f"{line} {word}" if line else word
            if self.font.size(candidate)[0] <= text_width:
                line = candidate
                continue
            if line:
                lines.append(line)
            # Long unbroken words must not extend beyond the canvas either.
            line = ""
            for char in word:
                if line and self.font.size(line + char)[0] > text_width:
                    lines.append(line)
                    line = char
                else:
                    line += char
        if line:
            lines.append(line)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            while lines[-1] and self.font.size(lines[-1] + "...")[0] > text_width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "..."
        lines = lines or [""]
        width = min(max_width, max(self.font.size(line)[0] for line in lines) + 28)
        surface = pygame.Surface((width, len(lines) * line_height + 20), pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 8, 6, 225), surface.get_rect(), border_radius=8)
        pygame.draw.rect(surface, (160, 130, 50, 240), surface.get_rect(), width=1, border_radius=8)
        for i, line in enumerate(lines):
            rendered = self._text(self.font, line, (254, 240, 180))
            surface.blit(rendered, ((width - rendered.get_width()) // 2, 10 + i * line_height))
        self._subtitle_cache_key = key
        self._subtitle_surface = surface
        return surface

    def _draw_magic_motes(self, canvas_rect: pygame.Rect) -> None:
        if not self.ambient_motes:
            return

        for x_ratio, y_ratio, speed, radius, phase in self.magic_motes:
            x = int(x_ratio * canvas_rect.width + math.sin(self.anim_time * 0.35 + phase) * 7)
            y_ratio_now = (y_ratio - self.anim_time * speed * 0.012) % 1.0
            y = int(y_ratio_now * canvas_rect.height)
            pulse = 0.55 + 0.45 * math.sin(self.anim_time * 1.8 + phase)
            # Tiny pre-rendered glow sprites replace a canvas-sized alpha surface.
            brightness = min(7, max(0, int(pulse * 7)))
            core_radius = max(1, int(radius * 2.0))
            key = (core_radius, brightness)
            mote = self._mote_sprites.get(key)
            extent = core_radius + 4
            if mote is None:
                mote = pygame.Surface((extent * 2 + 1, extent * 2 + 1), pygame.SRCALPHA)
                alpha = 45 + brightness * 80 // 7
                pygame.draw.circle(mote, (242, 196, 82, alpha // 3), (extent, extent), extent)
                pygame.draw.circle(mote, (255, 224, 132, alpha), (extent, extent), core_radius)
                self._mote_sprites[key] = mote
            self.screen.blit(mote, (canvas_rect.x + x - extent, canvas_rect.y + y - extent))

    def set_state(self, state: PortraitState) -> None:
        self.current_state = state

    def set_audio_amplitude(self, amplitude: float) -> None:
        self.audio_amplitude = max(0.0, min(1.0, amplitude))
        self.current_mouth_index = self.lipsync_engine.get_mouth_shape_index(self.audio_amplitude)
        if self.audio_amplitude < 0.05:
            self.set_viseme("X", self.audio_amplitude)
        elif self.current_mouth_index == 2:
            self.set_viseme("B", self.audio_amplitude)
        elif self.current_mouth_index == 3:
            self.set_viseme("C", self.audio_amplitude)
        else:
            self.set_viseme("X", self.audio_amplitude)

    def set_viseme(self, viseme: str, amplitude: Optional[float] = None) -> None:
        """Update active phonetic viseme (Preston-Blair standard) with smooth transitions."""
        v = str(viseme).strip().upper()
        if v not in VISEME_NAMES:
            v = "X"
        self.current_viseme = v
        self.lipsync_engine.set_active_viseme(self.current_viseme)
        self.current_mouth_index = self.lipsync_engine.viseme_to_legacy_index(self.current_viseme)
        if amplitude is not None:
            self.audio_amplitude = max(0.0, min(1.0, amplitude))

    def set_gaze_target(self, target_x: float, target_y: float, distance: float = 1.0) -> None:
        """Update visitor gaze coordinates from Hailo-8L / camera (-1.0 to 1.0)."""
        self.target_gaze_x = max(-1.0, min(1.0, float(target_x)))
        self.target_gaze_y = max(-1.0, min(1.0, float(target_y)))
        self.target_distance = max(0.4, min(2.5, float(distance)))

    def set_subtitle(self, text: str) -> None:
        self.subtitle_text = text

    def update_camera_frame(self, frame_surface: Optional[pygame.Surface], status_info: Optional[Dict[str, Any]] = None) -> None:
        self.camera_feed_surface = frame_surface
        if status_info:
            self.camera_status_info = status_info

    def set_latency_metric(self, key: str, value: str) -> None:
        self.latency_metrics[key] = value

    def toggle_camera_pip(self) -> None:
        self.show_camera_pip = not self.show_camera_pip
        print(f"[Renderer] Corner Camera PiP: {'ENABLED' if self.show_camera_pip else 'DISABLED'}")

    def toggle_debug_hud(self) -> None:
        self.show_debug_hud = not self.show_debug_hud

    def _draw_procedural_portrait(
        self,
        blink_stage: str,
        closure_progress: float,
        viseme: str,
        mouth_index: int,
        center_x: int,
        center_y: int,
        pupil_x: float,
        pupil_y: float,
        scale: float = 1.0,
    ) -> None:
        """Draws rich illuminated oil canvas of Wilhelm with gaze tracking, eased blinks, and visemes."""
        # Body & Knight Armor (Torso)
        pygame.draw.ellipse(self.screen, (75, 85, 95), (center_x - int(160*scale), center_y + int(40*scale), int(320*scale), int(220*scale)))
        # Crimson Gryffindor Sash
        pygame.draw.ellipse(self.screen, (150, 30, 30), (center_x - int(130*scale), center_y + int(55*scale), int(260*scale), int(60*scale)))
        # Curled White Aristocratic Wig
        pygame.draw.ellipse(self.screen, (230, 235, 240), (center_x - int(95*scale), center_y - int(30*scale), int(35*scale), int(75*scale)))
        pygame.draw.ellipse(self.screen, (230, 235, 240), (center_x + int(60*scale), center_y - int(30*scale), int(35*scale), int(75*scale)))
        pygame.draw.ellipse(self.screen, (235, 240, 245), (center_x - int(85*scale), center_y - int(100*scale), int(170*scale), int(65*scale)))
        # Face Oval
        head_rect = pygame.Rect(center_x - int(65*scale), center_y - int(55*scale), int(130*scale), int(140*scale))
        pygame.draw.ellipse(self.screen, (225, 190, 160), head_rect)
        # Eyebrows
        pygame.draw.arc(self.screen, (90, 65, 40), (center_x - int(45*scale), center_y - int(35*scale), int(35*scale), int(15*scale)), 0, 3.14, int(3*scale))
        pygame.draw.arc(self.screen, (90, 65, 40), (center_x + int(10*scale), center_y - int(35*scale), int(35*scale), int(15*scale)), 0, 3.14, int(3*scale))

        eye_y = center_y - int(18*scale)
        left_eye_x = center_x - int(32*scale)
        right_eye_x = center_x + int(32*scale)

        if blink_stage == "closed":
            # Fully closed eyelids
            pygame.draw.arc(self.screen, (60, 40, 25), (left_eye_x - int(14*scale), eye_y - int(4*scale), int(28*scale), int(12*scale)), 3.14, 6.28, int(3*scale))
            pygame.draw.arc(self.screen, (60, 40, 25), (right_eye_x - int(14*scale), eye_y - int(4*scale), int(28*scale), int(12*scale)), 3.14, 6.28, int(3*scale))
        else:
            # White Sclera
            pygame.draw.ellipse(self.screen, (245, 248, 250), (left_eye_x - int(14*scale), eye_y - int(8*scale), int(28*scale), int(16*scale)))
            pygame.draw.ellipse(self.screen, (245, 248, 250), (right_eye_x - int(14*scale), eye_y - int(8*scale), int(28*scale), int(16*scale)))

            # Pupil position clamped within eye boundaries
            max_px = int(6 * scale)
            max_py = int(3.5 * scale)
            px = max(-max_px, min(max_px, int(pupil_x * scale)))
            py = max(-max_py, min(max_py, int(pupil_y * scale)))

            # Blue-Grey Iris
            pygame.draw.circle(self.screen, (70, 110, 160), (left_eye_x + px, eye_y + py), int(6*scale))
            pygame.draw.circle(self.screen, (70, 110, 160), (right_eye_x + px, eye_y + py), int(6*scale))
            # Black Pupil
            pygame.draw.circle(self.screen, (15, 20, 30), (left_eye_x + px, eye_y + py), int(3*scale))
            pygame.draw.circle(self.screen, (15, 20, 30), (right_eye_x + px, eye_y + py), int(3*scale))
            # Specular Catchlight
            pygame.draw.circle(self.screen, (255, 255, 255), (left_eye_x + px - 1, eye_y + py - 1), max(1, int(1.5*scale)))
            pygame.draw.circle(self.screen, (255, 255, 255), (right_eye_x + px - 1, eye_y + py - 1), max(1, int(1.5*scale)))

            # Eased Half-Closed Eyelid Overlay
            if blink_stage == "half":
                drop_h = int(12 * scale * max(0.2, min(0.9, closure_progress)))
                pygame.draw.rect(self.screen, (225, 190, 160), (left_eye_x - int(14*scale), eye_y - int(8*scale), int(28*scale), drop_h))
                pygame.draw.rect(self.screen, (225, 190, 160), (right_eye_x - int(14*scale), eye_y - int(8*scale), int(28*scale), drop_h))
                pygame.draw.arc(self.screen, (80, 50, 35), (left_eye_x - int(14*scale), eye_y - int(8*scale) + drop_h - 2, int(28*scale), int(6*scale)), 3.14, 6.28, max(1, int(2*scale)))
                pygame.draw.arc(self.screen, (80, 50, 35), (right_eye_x - int(14*scale), eye_y - int(8*scale) + drop_h - 2, int(28*scale), int(6*scale)), 3.14, 6.28, max(1, int(2*scale)))

        # Nose
        pygame.draw.ellipse(self.screen, (205, 165, 135), (center_x - int(6*scale), center_y - int(4*scale), int(12*scale), int(20*scale)))
        # Mustache
        pygame.draw.ellipse(self.screen, (100, 70, 45), (center_x - int(24*scale), center_y + int(14*scale), int(26*scale), int(12*scale)))
        pygame.draw.ellipse(self.screen, (100, 70, 45), (center_x - int(2*scale), center_y + int(14*scale), int(26*scale), int(12*scale)))
        pygame.draw.circle(self.screen, (110, 75, 48), (center_x, center_y + int(12*scale)), int(7*scale))

        # Preston-Blair Viseme Mouth Rendering
        mouth_y = center_y + int(28*scale)
        if viseme in ("A", "X"):
            # Closed mouth / rest
            pygame.draw.ellipse(self.screen, (90, 35, 30), (center_x - int(16*scale), mouth_y, int(32*scale), int(4*scale)))
        elif viseme == "B":
            # Slightly parted consonants (K, S, T, D)
            pygame.draw.ellipse(self.screen, (65, 18, 18), (center_x - int(15*scale), mouth_y - int(2*scale), int(30*scale), int(8*scale)))
            pygame.draw.rect(self.screen, (240, 240, 240), (center_x - int(10*scale), mouth_y - int(2*scale), int(20*scale), int(3*scale)))
        elif viseme == "C":
            # Open vowels (EH, AE)
            pygame.draw.ellipse(self.screen, (60, 15, 15), (center_x - int(18*scale), mouth_y - int(4*scale), int(36*scale), int(13*scale)))
            pygame.draw.rect(self.screen, (245, 245, 245), (center_x - int(11*scale), mouth_y - int(4*scale), int(22*scale), int(4*scale)))
            pygame.draw.ellipse(self.screen, (175, 55, 65), (center_x - int(8*scale), mouth_y + int(3*scale), int(16*scale), int(6*scale)))
        elif viseme == "D":
            # Wide open vowels (AA, AO)
            pygame.draw.ellipse(self.screen, (45, 10, 10), (center_x - int(20*scale), mouth_y - int(6*scale), int(40*scale), int(20*scale)))
            pygame.draw.rect(self.screen, (250, 250, 250), (center_x - int(13*scale), mouth_y - int(6*scale), int(26*scale), int(5*scale)))
            pygame.draw.ellipse(self.screen, (185, 65, 75), (center_x - int(10*scale), mouth_y + int(4*scale), int(20*scale), int(8*scale)))
        elif viseme == "E":
            # Rounded vowels (O, OW, ER)
            pygame.draw.ellipse(self.screen, (50, 12, 12), (center_x - int(12*scale), mouth_y - int(5*scale), int(24*scale), int(14*scale)))
            pygame.draw.rect(self.screen, (240, 240, 240), (center_x - int(7*scale), mouth_y - int(5*scale), int(14*scale), int(3*scale)))
        elif viseme == "F":
            # Puckered lips (UW, W, OO)
            pygame.draw.circle(self.screen, (55, 14, 14), (center_x, mouth_y + int(2*scale)), int(7*scale))
            pygame.draw.circle(self.screen, (230, 230, 230), (center_x, mouth_y + int(1*scale)), int(3*scale))
        elif viseme == "G":
            # Labiodental (upper teeth on lower lip: F, V)
            pygame.draw.ellipse(self.screen, (70, 20, 20), (center_x - int(14*scale), mouth_y - int(2*scale), int(28*scale), int(8*scale)))
            pygame.draw.rect(self.screen, (248, 248, 248), (center_x - int(10*scale), mouth_y - int(2*scale), int(20*scale), int(4*scale)))
        elif viseme == "H":
            # Tongue against teeth (L, TH)
            pygame.draw.ellipse(self.screen, (55, 15, 15), (center_x - int(16*scale), mouth_y - int(4*scale), int(32*scale), int(14*scale)))
            pygame.draw.rect(self.screen, (240, 240, 240), (center_x - int(10*scale), mouth_y - int(4*scale), int(20*scale), int(3*scale)))
            pygame.draw.ellipse(self.screen, (190, 70, 80), (center_x - int(7*scale), mouth_y - int(1*scale), int(14*scale), int(7*scale)))
        else:
            # Fallback legacy 1, 2, 3
            if mouth_index == 1:
                pygame.draw.ellipse(self.screen, (90, 35, 30), (center_x - int(16*scale), mouth_y, int(32*scale), int(4*scale)))
            elif mouth_index == 2:
                pygame.draw.ellipse(self.screen, (65, 18, 18), (center_x - int(16*scale), mouth_y - int(4*scale), int(32*scale), int(12*scale)))
                pygame.draw.rect(self.screen, (245, 245, 245), (center_x - int(9*scale), mouth_y - int(4*scale), int(18*scale), int(4*scale)))
            else:
                pygame.draw.ellipse(self.screen, (45, 10, 10), (center_x - int(20*scale), mouth_y - int(6*scale), int(40*scale), int(20*scale)))
                pygame.draw.rect(self.screen, (250, 250, 250), (center_x - int(12*scale), mouth_y - int(6*scale), int(24*scale), int(5*scale)))
                pygame.draw.ellipse(self.screen, (185, 65, 75), (center_x - int(10*scale), mouth_y + int(4*scale), int(20*scale), int(8*scale)))

    def render(self) -> None:
        """Main frame render call."""
        w, h = self.screen.get_size()
        center_x = w // 2
        if (w, h) != self._viewport_size:
            # Resizing must not retain a full set of paintings at every past size.
            self._scaled_sprite_cache.clear()
            self._viewport_size = (w, h)
        now = time.monotonic()
        delta = min(0.1, max(0.0, now - self._last_render_time))
        self._last_render_time = now
        self.anim_time += delta
        self.blink_controller.update()
        blink_stage = self.blink_controller.get_stage()
        closure_progress = self.blink_controller.get_progress()

        # Smooth exponential interpolation toward target gaze from Hailo vision
        if self.gaze_tracking_enabled:
            gaze_alpha = 1.0 - math.exp(-7.7 * delta)
            distance_alpha = 1.0 - math.exp(-5.0 * delta)
            self.current_gaze_x += (self.target_gaze_x - self.current_gaze_x) * gaze_alpha
            self.current_gaze_y += (self.target_gaze_y - self.current_gaze_y) * gaze_alpha
            self.current_distance += (self.target_distance - self.current_distance) * distance_alpha
        else:
            gaze_alpha = 1.0 - math.exp(-5.0 * delta)
            self.current_gaze_x += (0.0 - self.current_gaze_x) * gaze_alpha
            self.current_gaze_y += (0.0 - self.current_gaze_y) * gaze_alpha

        # Saccade micro-movements
        saccade_x, saccade_y = self.saccade_controller.update()
        self.eye_offset_x = (self.current_gaze_x * 8.0 * self.gaze_sensitivity_x) + saccade_x
        self.eye_offset_y = (self.current_gaze_y * 5.0 * self.gaze_sensitivity_y) + saccade_y

        # Kinematic decoupled offsets
        head_yaw_x = self.current_gaze_x * 4.5 * self.gaze_sensitivity_x
        head_pitch_y = self.current_gaze_y * 3.0 * self.gaze_sensitivity_y
        bg_drift_x = -self.current_gaze_x * 6.0
        bg_drift_y = -self.current_gaze_y * 3.5
        breath_offset = math.sin(self.anim_time * 1.5) * 2.5

        # 1. Dark Castle Wall Background
        self.screen.fill((20, 18, 16))

        # 2. Ornate Picture Frame (Outer and Gilded Inner Molding)
        frame_margin_x = int(w * 0.04)
        frame_margin_y = int(h * 0.04)
        frame_rect = pygame.Rect(frame_margin_x, frame_margin_y, w - frame_margin_x * 2, h - frame_margin_y * 2)
        
        # Outer Gold Bevel
        pygame.draw.rect(self.screen, (75, 55, 25), frame_rect, width=18, border_radius=12)
        pygame.draw.rect(self.screen, (190, 150, 50), frame_rect.inflate(-16, -16), width=6, border_radius=8)
        pygame.draw.rect(self.screen, (230, 195, 75), frame_rect.inflate(-24, -24), width=2, border_radius=6)

        # Inner Canvas Viewport
        canvas_rect = frame_rect.inflate(-36, -36)
        pygame.draw.rect(self.screen, (28, 24, 22), canvas_rect)

        # 3. Layered Sprite Rendering (or Procedural fallback)
        bg_sprite = self.sprites.get("background")
        torso_sprite = self.sprites.get("torso")
        base_sprite = self.sprites.get("base")
        eyes_closed_sprite = self.sprites.get("eyes_closed")
        eyes_half_sprite = self.sprites.get("eyes_half")

        viseme_sprite_key = f"viseme_{self.current_viseme}"
        viseme_sprite = self.sprites.get(viseme_sprite_key)
        mouth_sprite_key = f"mouth_{self.current_mouth_index}"
        mouth_sprite = viseme_sprite or self.sprites.get(mouth_sprite_key)

        previous_clip = self.screen.get_clip()
        self.screen.set_clip(canvas_rect)

        # Optional separate background layer with counter-parallax
        if bg_sprite is not None:
            bg_w, bg_h = bg_sprite.get_size()
            bg_scale = max(canvas_rect.width / bg_w, canvas_rect.height / bg_h) * 1.05
            bg_size = (int(bg_w * bg_scale), int(bg_h * bg_scale))
            bg_dest_x = canvas_rect.centerx - bg_size[0] // 2 + int(bg_drift_x)
            bg_dest_y = canvas_rect.centery - bg_size[1] // 2 + int(bg_drift_y)
            scaled_bg = self._scaled_sprite("background", bg_sprite, bg_size)
            self.screen.blit(scaled_bg, (bg_dest_x, bg_dest_y))

        if base_sprite is not None and self.asset_mode == "full_frames":
            if blink_stage == "closed" and eyes_closed_sprite is not None:
                frame_key = "eyes_closed"
            elif blink_stage == "half" and eyes_half_sprite is not None:
                frame_key = "eyes_half"
            elif self.current_viseme not in ("X", "A") and viseme_sprite is not None:
                frame_key = viseme_sprite_key
            elif self.current_mouth_index > 1 and mouth_sprite is not None:
                frame_key = mouth_sprite_key
            else:
                frame_key = "base"

            frame_sprite = self.sprites.get(frame_key) or base_sprite
            bw, bh = frame_sprite.get_size()
            overscan = 1.025 if self.camera_motion else 1.0
            scale = max(canvas_rect.width / bw, canvas_rect.height / bh) * overscan
            target_size = (int(bw * scale), int(bh * scale))
            drift_x = (math.sin(self.anim_time * 0.23) * 3.0 if self.camera_motion else 0.0) + head_yaw_x
            drift_y = (breath_offset + (math.sin(self.anim_time * 0.17) * 2.0 if self.camera_motion else 0.0)) + head_pitch_y
            dest_x = canvas_rect.centerx - target_size[0] // 2 + int(drift_x)
            dest_y = canvas_rect.centery - target_size[1] // 2 + int(drift_y)

            scaled_frame = self._scaled_sprite(frame_key, frame_sprite, target_size)
            self.screen.blit(scaled_frame, (dest_x, dest_y))
            self._draw_magic_motes(canvas_rect)
        elif base_sprite is not None:
            # Multi-layer decoupled 2.5D rendering
            bw, bh = base_sprite.get_size()
            scale = min(canvas_rect.width / bw, canvas_rect.height / bh)
            target_size = (int(bw * scale), int(bh * scale))

            # Torso layer (independent breathing)
            torso_dest_x = canvas_rect.centerx - target_size[0] // 2
            torso_dest_y = canvas_rect.centery - target_size[1] // 2 + int(breath_offset)
            if torso_sprite is not None:
                scaled_torso = self._scaled_sprite("torso", torso_sprite, target_size)
                self.screen.blit(scaled_torso, (torso_dest_x, torso_dest_y))

            # Head / Base layer (with head yaw and gaze offset)
            head_dest_x = canvas_rect.centerx - target_size[0] // 2 + int(head_yaw_x)
            head_dest_y = canvas_rect.centery - target_size[1] // 2 + int(breath_offset * 0.3 + head_pitch_y)

            scaled_base = self._scaled_sprite("base", base_sprite, target_size)
            self.screen.blit(scaled_base, (head_dest_x, head_dest_y))

            # Eyelids layer (multi-stage biological blink)
            if blink_stage == "closed" and eyes_closed_sprite is not None:
                scaled_eyes = self._scaled_sprite("eyes_closed", eyes_closed_sprite, target_size)
                self.screen.blit(scaled_eyes, (head_dest_x, head_dest_y))
            elif blink_stage == "half":
                if eyes_half_sprite is not None:
                    scaled_half = self._scaled_sprite("eyes_half", eyes_half_sprite, target_size)
                    self.screen.blit(scaled_half, (head_dest_x, head_dest_y))
                elif eyes_closed_sprite is not None:
                    # Clip closed eye sprite halfway for smooth intermediate blink
                    scaled_eyes = self._scaled_sprite("eyes_closed", eyes_closed_sprite, target_size)
                    half_clip = pygame.Rect(head_dest_x, head_dest_y, target_size[0], int(target_size[1] * 0.55))
                    self.screen.set_clip(half_clip.clip(canvas_rect))
                    self.screen.blit(scaled_eyes, (head_dest_x, head_dest_y))
                    self.screen.set_clip(canvas_rect)

            # Mouth / Viseme layer
            if mouth_sprite is not None:
                mouth_key = viseme_sprite_key if viseme_sprite is not None else mouth_sprite_key
                scaled_mouth = self._scaled_sprite(mouth_key, mouth_sprite, target_size)
                self.screen.blit(scaled_mouth, (head_dest_x, head_dest_y))

            self._draw_magic_motes(canvas_rect)
        else:
            # Rich procedural painting with full gaze tracking & visemes
            self._draw_procedural_portrait(
                blink_stage=blink_stage,
                closure_progress=closure_progress,
                viseme=self.current_viseme,
                mouth_index=self.current_mouth_index,
                center_x=canvas_rect.centerx + int(head_yaw_x),
                center_y=canvas_rect.centery + int(breath_offset + head_pitch_y),
                pupil_x=self.eye_offset_x,
                pupil_y=self.eye_offset_y,
                scale=min(w / 800.0, h / 600.0),
            )
            self._draw_magic_motes(canvas_rect)

        self.screen.set_clip(previous_clip)

        # 4. Status Plate & Dialogue Subtitles at Bottom
        plate_w = max(80, min(w - 64, 860))
        plate_h = 42
        plate_x = center_x - plate_w // 2
        plate_y = h - frame_margin_y - 65

        plate_rect = pygame.Rect(plate_x, plate_y, plate_w, plate_h)
        pygame.draw.rect(self.screen, (15, 14, 12), plate_rect, border_radius=8)
        pygame.draw.rect(self.screen, (180, 140, 45), plate_rect, width=2, border_radius=8)

        # State Badge Styling
        state_colors = {
            PortraitState.IDLE: ((160, 160, 160), "Approach the portrait"),
            PortraitState.WAKE_PENDING: ((234, 179, 8), "A visitor approaches..."),
            PortraitState.GREETING: ((250, 204, 21), "Welcome, traveller"),
            PortraitState.LISTENING: ((56, 189, 248), "Listening - speak freely"),
            PortraitState.THINKING: ((192, 132, 252), "Considering your words..."),
            PortraitState.SPEAKING: ((251, 146, 60), "Wilhelm speaks"),
            PortraitState.COOLDOWN: ((148, 163, 184), "Until we meet again"),
        }
        badge_color, state_label = state_colors.get(self.current_state, ((200, 200, 200), self.current_state.value))

        state_badge_surf = self._text(self.badge_font, state_label, badge_color)
        pygame.draw.circle(self.screen, badge_color, (plate_x + 19, plate_y + plate_h // 2), 4)
        self.screen.blit(state_badge_surf, (plate_x + 32, plate_y + (plate_h - state_badge_surf.get_height()) // 2))

        # Audio VU / Amplitude Bar on plate when speaking/listening
        if plate_w > 420 and self.current_state in (PortraitState.SPEAKING, PortraitState.LISTENING):
            vu_x = plate_x + plate_w - 160
            vu_y = plate_y + 14
            pygame.draw.rect(self.screen, (40, 40, 40), (vu_x, vu_y, 140, 14), border_radius=4)
            fill_w = int(min(1.0, max(0.0, self.audio_amplitude * 2.2)) * 136)
            if fill_w > 0:
                pygame.draw.rect(self.screen, (251, 146, 60) if self.current_state == PortraitState.SPEAKING else (56, 189, 248), (vu_x + 2, vu_y + 2, fill_w, 10), border_radius=3)

        # Spoken Dialogue Subtitle Banner
        if self.subtitle_text:
            sub_surf = self._get_subtitle_surface(max(40, canvas_rect.width - 32), max(50, h // 3))
            sub_rect = sub_surf.get_rect(midbottom=(center_x, plate_y - 12))
            self.screen.blit(sub_surf, sub_rect)

        # 5. Corner Camera Picture-in-Picture (PiP) Feed
        if self.show_camera_pip and self.camera_feed_surface is not None:
            pip_w = 200
            pip_h = 150
            pip_x = w - frame_margin_x - pip_w - 24
            pip_y = frame_margin_y + 24

            # Background & Outer Cyber/Gold Viewfinder Frame
            pip_rect = pygame.Rect(pip_x, pip_y, pip_w, pip_h)
            pygame.draw.rect(self.screen, (10, 14, 18), pip_rect, border_radius=6)

            # Draw scaled camera video frame
            if self.camera_feed_surface is not self._camera_preview_source:
                self._camera_preview_source = self.camera_feed_surface
                self._camera_preview = self.camera_feed_surface
                if self.camera_feed_surface.get_size() != (pip_w, pip_h):
                    self._camera_preview = pygame.transform.smoothscale(self.camera_feed_surface, (pip_w, pip_h))
            self.screen.blit(self._camera_preview, (pip_x, pip_y))

            # Viewfinder Target Borders
            pygame.draw.rect(self.screen, (52, 211, 153), pip_rect, width=2, border_radius=6)
            
            # Corner Camera Top Header Label
            header_rect = pygame.Rect(pip_x, pip_y, pip_w, 20)
            pygame.draw.rect(self.screen, (8, 12, 16, 200), header_rect)
            cam_fps = self.camera_status_info.get("fps", 30.0)
            cam_header_surf = self._text(self.hud_font, f"PI5 CAM ({cam_fps:.0f}FPS)", (56, 189, 248))
            self.screen.blit(cam_header_surf, (pip_x + 8, pip_y + 4))

            # Detected presence indicator
            if self.camera_status_info.get("detected", False):
                conf = self.camera_status_info.get("confidence", 0.9)
                detector_label = "MOTION" if self.camera_status_info.get("detector") == "motion" else "VISITOR"
                det_surf = self._text(self.hud_font, f"{detector_label} {int(conf*100)}%", (52, 211, 153))
                self.screen.blit(det_surf, (pip_x + 8, pip_y + pip_h - 18))

        # 6. Latency Metrics & Debug HUD
        if self.show_debug_hud:
            hud_y = frame_margin_y + 24
            hud_x = frame_margin_x + 24
            
            hud_bg = pygame.Rect(hud_x, hud_y, 360, 158)
            pygame.draw.rect(self.screen, (10, 12, 15, 215), hud_bg, border_radius=6)
            pygame.draw.rect(self.screen, (50, 65, 80), hud_bg, width=1, border_radius=6)

            mode_label = self.latency_metrics.get("mode", "LOCAL OFFLINE")
            lines = [
                f"TALKING PORTRAIT [{mode_label}]",
                f"STT Latency:    {self.latency_metrics.get('stt', '--')}",
                f"LLM TTFT:       {self.latency_metrics.get('llm_ttft', '--')}",
                f"TTS / Audio:    {self.latency_metrics.get('tts', '--')}",
                f"Turnaround:     {self.latency_metrics.get('turnaround', '--')}",
                f"Token Quota:    {self.latency_metrics.get('quota', '100% LOCAL')}",
                f"Gaze Tracking:  ({self.current_gaze_x:+.2f}, {self.current_gaze_y:+.2f}) Dist: {self.current_distance:.1f}",
                f"Viseme/Eyelids: Viseme_{self.current_viseme} (Mouth_{self.current_mouth_index}) | {self.blink_controller.get_stage().upper()}",
            ]
            for i, line in enumerate(lines):
                color = (250, 204, 21) if i == 0 else (200, 220, 240)
                surf = self._text(self.hud_font, line, color)
                self.screen.blit(surf, (hud_x + 10, hud_y + 8 + i * 17))

        # 7. Hotkey Controls Help Bar at very bottom
        help_text = "[SPACE] Wake | [T] Talk | [C] Camera | [H] Details | [ESC] Quit"
        help_surf = self._text(self.hud_font, help_text, (130, 120, 100))
        self.screen.blit(help_surf, (center_x - help_surf.get_width() // 2, h - 22))

        pygame.display.flip()
        self.clock.tick(self.fps)

    def cleanup(self) -> None:
        try:
            pygame.quit()
        except Exception:
            pass
