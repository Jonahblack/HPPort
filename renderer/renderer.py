"""Pygame-based Talking Portrait graphics renderer with layered sprite compositing & corner camera PiP feed."""

import os
import time
import math
import pygame
from typing import Dict, Any, Optional, Tuple
from state_machine import PortraitState
from renderer.animation import BlinkController, LipSyncEngine


class PortraitRenderer:
    """Renders layered portrait artwork: Base -> Eyes Overlay -> Mouth Shapes (1,2,3) -> Subtitles -> Camera PiP -> HUD."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("renderer", {})
        self.width = int(self.config.get("width", 1024))
        self.height = int(self.config.get("height", 768))
        self.fullscreen = bool(self.config.get("fullscreen", False))
        self.fps = int(self.config.get("fps", 60))
        self.assets_dir = self.config.get("assets_dir", "assets")

        pygame.init()
        pygame.font.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass

        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        pygame.display.set_caption(self.config.get("window_title", "Harry Potter Talking Portrait (Gemma 4)"))

        self.clock = pygame.time.Clock()
        
        # Load System Fonts
        self.title_font = pygame.font.SysFont("Georgia", 24, bold=True)
        self.font = pygame.font.SysFont("Georgia", 20, italic=True)
        self.hud_font = pygame.font.SysFont("Courier New", 13, bold=True)
        self.badge_font = pygame.font.SysFont("Georgia", 14, bold=True)

        # Animation controllers
        self.blink_controller = BlinkController(
            min_interval_sec=float(self.config.get("blink_min_seconds", 2.0)),
            max_interval_sec=float(self.config.get("blink_max_seconds", 5.0)),
            blink_duration_ms=int(self.config.get("blink_duration_ms", 150)),
        )
        self.lipsync_engine = LipSyncEngine(
            threshold_mouth_2=float(self.config.get("amplitude_threshold_mouth_2", 0.15)),
            threshold_mouth_3=float(self.config.get("amplitude_threshold_mouth_3", 0.45)),
        )

        # Sprites dictionary
        self.sprites: Dict[str, Optional[pygame.Surface]] = {}
        self._load_sprites()

        # State and animation variables
        self.current_state = PortraitState.IDLE
        self.current_mouth_index = 1
        self.audio_amplitude = 0.0
        self.subtitle_text = ""
        self.show_debug_hud = True
        self.show_camera_pip = True
        self.camera_feed_surface: Optional[pygame.Surface] = None
        self.camera_status_info: Dict[str, Any] = {}

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
        self.eye_offset_x = 0.0

    def _load_sprites(self) -> None:
        """Load sprite image layers from assets directory with fallback naming support."""
        filenames = {
            "base": ["base.png", "cadogan_base.png"],
            "eyes_closed": ["eyes_closed.png", "cadogan_eyes_closed.png"],
            "mouth_1": ["mouth_1.png", "cadogan_mouth_1.png"],
            "mouth_2": ["mouth_2.png", "cadogan_mouth_2.png"],
            "mouth_3": ["mouth_3.png", "cadogan_mouth_3.png"],
        }

        for key, candidates in filenames.items():
            loaded = False
            for fname in candidates:
                path = os.path.join(self.assets_dir, fname)
                if os.path.exists(path):
                    try:
                        img = pygame.image.load(path).convert_alpha()
                        self.sprites[key] = img
                        print(f"[Renderer] Loaded sprite layer '{key}': {path}")
                        loaded = True
                        break
                    except Exception as e:
                        print(f"[Renderer] Failed to load {path}: {e}")
            if not loaded:
                self.sprites[key] = None

    def set_state(self, state: PortraitState) -> None:
        self.current_state = state

    def set_audio_amplitude(self, amplitude: float) -> None:
        self.audio_amplitude = amplitude
        self.current_mouth_index = self.lipsync_engine.get_mouth_shape_index(amplitude)

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

    def _draw_procedural_portrait(self, is_eyes_closed: bool, mouth_index: int, center_x: int, center_y: int, scale: float = 1.0) -> None:
        """Draws rich illuminated oil canvas of Lord Cadogan if PNG sprites are not found."""
        # Body & Knight Armor
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

        if is_eyes_closed:
            pygame.draw.arc(self.screen, (60, 40, 25), (left_eye_x - int(14*scale), eye_y - int(6*scale), int(28*scale), int(14*scale)), 3.14, 6.28, int(3*scale))
            pygame.draw.arc(self.screen, (60, 40, 25), (right_eye_x - int(14*scale), eye_y - int(6*scale), int(28*scale), int(14*scale)), 3.14, 6.28, int(3*scale))
        else:
            pygame.draw.ellipse(self.screen, (245, 248, 250), (left_eye_x - int(14*scale), eye_y - int(8*scale), int(28*scale), int(16*scale)))
            pygame.draw.ellipse(self.screen, (245, 248, 250), (right_eye_x - int(14*scale), eye_y - int(8*scale), int(28*scale), int(16*scale)))
            # Iris
            pygame.draw.circle(self.screen, (70, 110, 160), (left_eye_x + int(self.eye_offset_x*scale), eye_y), int(6*scale))
            pygame.draw.circle(self.screen, (70, 110, 160), (right_eye_x + int(self.eye_offset_x*scale), eye_y), int(6*scale))
            # Pupil + Catchlight
            pygame.draw.circle(self.screen, (15, 20, 30), (left_eye_x + int(self.eye_offset_x*scale), eye_y), int(3*scale))
            pygame.draw.circle(self.screen, (15, 20, 30), (right_eye_x + int(self.eye_offset_x*scale), eye_y), int(3*scale))
            pygame.draw.circle(self.screen, (255, 255, 255), (left_eye_x - 1, eye_y - 1), max(1, int(1.5*scale)))
            pygame.draw.circle(self.screen, (255, 255, 255), (right_eye_x - 1, eye_y - 1), max(1, int(1.5*scale)))

        # Nose
        pygame.draw.ellipse(self.screen, (205, 165, 135), (center_x - int(6*scale), center_y - int(4*scale), int(12*scale), int(20*scale)))
        # Mustache
        pygame.draw.ellipse(self.screen, (100, 70, 45), (center_x - int(24*scale), center_y + int(14*scale), int(26*scale), int(12*scale)))
        pygame.draw.ellipse(self.screen, (100, 70, 45), (center_x - int(2*scale), center_y + int(14*scale), int(26*scale), int(12*scale)))
        pygame.draw.circle(self.screen, (110, 75, 48), (center_x, center_y + int(12*scale), int(7*scale)))

        # Mouth Lip Sync
        mouth_y = center_y + int(28*scale)
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
        center_y = h // 2

        self.anim_time += 0.02
        is_blinking = self.blink_controller.update()
        self.eye_offset_x = math.sin(self.anim_time * 0.8) * 3.0
        breath_offset = math.sin(self.anim_time * 1.5) * 2.0

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
        base_sprite = self.sprites.get("base")
        eyes_closed_sprite = self.sprites.get("eyes_closed")
        mouth_sprite_key = f"mouth_{self.current_mouth_index}"
        mouth_sprite = self.sprites.get(mouth_sprite_key)

        if base_sprite is not None:
            # Scale to fit inner canvas keeping aspect ratio
            bw, bh = base_sprite.get_size()
            scale = min(canvas_rect.width / bw, canvas_rect.height / bh)
            target_size = (int(bw * scale), int(bh * scale))

            dest_x = canvas_rect.centerx - target_size[0] // 2
            dest_y = canvas_rect.centery - target_size[1] // 2 + int(breath_offset)

            # Draw Layer 1: Base Portrait
            scaled_base = pygame.transform.smoothscale(base_sprite, target_size)
            self.screen.blit(scaled_base, (dest_x, dest_y))

            # Draw Layer 2: Eyes Closed Overlay (when blinking)
            if is_blinking and eyes_closed_sprite is not None:
                scaled_eyes = pygame.transform.smoothscale(eyes_closed_sprite, target_size)
                self.screen.blit(scaled_eyes, (dest_x, dest_y))

            # Draw Layer 3: Mouth Overlay (Mouth 1, 2, 3)
            if mouth_sprite is not None:
                scaled_mouth = pygame.transform.smoothscale(mouth_sprite, target_size)
                self.screen.blit(scaled_mouth, (dest_x, dest_y))
        else:
            # High quality procedural painting
            self._draw_procedural_portrait(
                is_blinking,
                self.current_mouth_index,
                canvas_rect.centerx,
                canvas_rect.centery + int(breath_offset),
                scale=min(w / 800.0, h / 600.0),
            )

        # 4. Status Plate & Dialogue Subtitles at Bottom
        plate_w = min(w - 120, 860)
        plate_h = 42
        plate_x = center_x - plate_w // 2
        plate_y = h - frame_margin_y - 65

        plate_rect = pygame.Rect(plate_x, plate_y, plate_w, plate_h)
        pygame.draw.rect(self.screen, (15, 14, 12), plate_rect, border_radius=8)
        pygame.draw.rect(self.screen, (180, 140, 45), plate_rect, width=2, border_radius=8)

        # State Badge Styling
        state_colors = {
            PortraitState.IDLE: ((160, 160, 160), "IDLE (WAITING)"),
            PortraitState.WAKE_PENDING: ((234, 179, 8), "WAKE PENDING (APPROACHING)"),
            PortraitState.GREETING: ((250, 204, 21), "GREETING VISITOR"),
            PortraitState.LISTENING: ((56, 189, 248), "LISTENING 🎙️ (SPEAK NOW)"),
            PortraitState.THINKING: ((192, 132, 252), "THINKING 🧠 (GEMMA 4)"),
            PortraitState.SPEAKING: ((251, 146, 60), "SPEAKING 🔊 (PIPER TTS)"),
            PortraitState.COOLDOWN: ((148, 163, 184), "COOLDOWN (RESTING)"),
        }
        badge_color, state_label = state_colors.get(self.current_state, ((200, 200, 200), self.current_state.value))

        state_badge_surf = self.badge_font.render(f"● {state_label}", True, badge_color)
        self.screen.blit(state_badge_surf, (plate_x + 16, plate_y + 12))

        # Audio VU / Amplitude Bar on plate when speaking/listening
        if self.current_state in (PortraitState.SPEAKING, PortraitState.LISTENING):
            vu_x = plate_x + plate_w - 160
            vu_y = plate_y + 14
            pygame.draw.rect(self.screen, (40, 40, 40), (vu_x, vu_y, 140, 14), border_radius=4)
            fill_w = int(min(1.0, max(0.0, self.audio_amplitude * 2.2)) * 136)
            if fill_w > 0:
                pygame.draw.rect(self.screen, (251, 146, 60) if self.current_state == PortraitState.SPEAKING else (56, 189, 248), (vu_x + 2, vu_y + 2, fill_w, 10), border_radius=3)

        # Spoken Dialogue Subtitle Banner
        if self.subtitle_text:
            sub_surf = self.font.render(f"« {self.subtitle_text} »", True, (254, 240, 138))
            sub_rect = sub_surf.get_rect(center=(center_x, plate_y - 28))
            sub_bg = sub_rect.inflate(28, 14)
            pygame.draw.rect(self.screen, (10, 8, 6, 220), sub_bg, border_radius=6)
            pygame.draw.rect(self.screen, (160, 130, 50), sub_bg, width=1, border_radius=6)
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
            scaled_cam = pygame.transform.smoothscale(self.camera_feed_surface, (pip_w, pip_h))
            self.screen.blit(scaled_cam, (pip_x, pip_y))

            # Viewfinder Target Borders
            pygame.draw.rect(self.screen, (52, 211, 153), pip_rect, width=2, border_radius=6)
            
            # Corner Camera Top Header Label
            header_rect = pygame.Rect(pip_x, pip_y, pip_w, 20)
            pygame.draw.rect(self.screen, (8, 12, 16, 200), header_rect)
            cam_driver_label = self.camera_status_info.get("driver", "camera")
            cam_fps = self.camera_status_info.get("fps", 30.0)
            cam_header_surf = self.hud_font.render(f"PI5 CAM ({cam_fps:.0f}FPS)", True, (56, 189, 248))
            self.screen.blit(cam_header_surf, (pip_x + 8, pip_y + 4))

            # Detected presence indicator
            if self.camera_status_info.get("detected", False):
                conf = self.camera_status_info.get("confidence", 0.9)
                det_surf = self.hud_font.render(f"PERSON {int(conf*100)}%", True, (52, 211, 153))
                self.screen.blit(det_surf, (pip_x + 8, pip_y + pip_h - 18))

        # 6. Latency Metrics & Debug HUD
        if self.show_debug_hud:
            hud_y = frame_margin_y + 24
            hud_x = frame_margin_x + 24
            
            hud_bg = pygame.Rect(hud_x, hud_y, 340, 110)
            pygame.draw.rect(self.screen, (10, 12, 15, 210), hud_bg, border_radius=6)
            pygame.draw.rect(self.screen, (50, 65, 80), hud_bg, width=1, border_radius=6)

            lines = [
                f"TALKING PORTRAIT (GEMMA 4 ON PI 5)",
                f"STT Latency:    {self.latency_metrics.get('stt', '--')}",
                f"Gemma TTFT:     {self.latency_metrics.get('llm_ttft', '--')}",
                f"Piper TTS:      {self.latency_metrics.get('tts', '--')}",
                f"Turnaround:     {self.latency_metrics.get('turnaround', '--')}",
                f"Mouth Shape:    Mouth_{self.current_mouth_index} (RMS: {self.audio_amplitude:.2f})",
            ]
            for i, line in enumerate(lines):
                color = (250, 204, 21) if i == 0 else (200, 220, 240)
                surf = self.hud_font.render(line, True, color)
                self.screen.blit(surf, (hud_x + 10, hud_y + 8 + i * 16))

        # 7. Hotkey Controls Help Bar at very bottom
        help_text = "[SPACE] Wake Visitor | [T] Talk/STT | [C] Camera PiP | [H] Toggle HUD | [ESC] Quit"
        help_surf = self.hud_font.render(help_text, True, (130, 120, 100))
        self.screen.blit(help_surf, (center_x - help_surf.get_width() // 2, h - 22))

        pygame.display.flip()
        self.clock.tick(self.fps)

    def cleanup(self) -> None:
        try:
            pygame.quit()
        except Exception:
            pass
