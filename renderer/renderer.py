"""Pygame-based Talking Portrait graphics renderer with layered sprite compositing."""

import os
import pygame
from typing import Dict, Any, Optional
from state_machine import PortraitState
from renderer.animation import BlinkController, LipSyncEngine


class PortraitRenderer:
    """Renders layered portrait artwork: Base -> Eyes Overlay -> Mouth Shapes (1,2,3) -> HUD."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("renderer", {})
        self.width = self.config.get("width", 1024)
        self.height = self.config.get("height", 768)
        self.fullscreen = self.config.get("fullscreen", False)
        self.fps = self.config.get("fps", 60)
        self.assets_dir = self.config.get("assets_dir", "assets")

        pygame.init()
        pygame.font.init()
        pygame.mixer.init()

        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((self.width, self.height), flags)
        pygame.display.set_caption(self.config.get("window_title", "Harry Potter Talking Portrait"))

        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Georgia", 22)
        self.hud_font = pygame.font.SysFont("Courier New", 14)

        # Animation controllers
        self.blink_controller = BlinkController(
            min_interval_sec=self.config.get("blink_min_seconds", 2.0),
            max_interval_sec=self.config.get("blink_max_seconds", 5.0),
            blink_duration_ms=self.config.get("blink_duration_ms", 150),
        )
        self.lipsync_engine = LipSyncEngine(
            threshold_mouth_2=self.config.get("amplitude_threshold_mouth_2", 0.15),
            threshold_mouth_3=self.config.get("amplitude_threshold_mouth_3", 0.45),
        )

        # Sprites
        self.sprites: Dict[str, Optional[pygame.Surface]] = {}
        self._load_sprites()

        # State and animation variables
        self.current_state = PortraitState.IDLE
        self.current_mouth_index = 1
        self.audio_amplitude = 0.0
        self.subtitle_text = ""
        self.show_debug_hud = True

    def _load_sprites(self) -> None:
        """Load sprite image layers from assets directory with graceful fallback."""
        filenames = {
            "base": "cadogan_base.png",
            "eyes_closed": "cadogan_eyes_closed.png",
            "mouth_1": "cadogan_mouth_1.png",
            "mouth_2": "cadogan_mouth_2.png",
            "mouth_3": "cadogan_mouth_3.png",
            "frame": "frame_gold.png",
        }

        for key, fname in filenames.items():
            path = os.path.join(self.assets_dir, fname)
            if os.path.exists(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    self.sprites[key] = img
                    print(f"[Renderer] Loaded sprite: {fname}")
                except Exception as e:
                    print(f"[Renderer] Failed to load {path}: {e}")
                    self.sprites[key] = None
            else:
                self.sprites[key] = None

    def set_state(self, state: PortraitState) -> None:
        self.current_state = state

    def set_audio_amplitude(self, amplitude: float) -> None:
        self.audio_amplitude = amplitude
        self.current_mouth_index = self.lipsync_engine.get_mouth_shape_index(amplitude)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_text = text

    def draw_fallback_portrait(self, is_eyes_closed: bool, mouth_index: int) -> None:
        """Draw a procedural medieval oil portrait canvas if sprite assets are missing."""
        w, h = self.screen.get_size()
        center_x, center_y = w // 2, h // 2

        # 1. Canvas Background (Rich antique parchment / dark castle wall)
        self.screen.fill((28, 24, 20))

        # 2. Ornate Gilded Picture Frame
        frame_rect = pygame.Rect(40, 40, w - 80, h - 80)
        pygame.draw.rect(self.screen, (90, 70, 30), frame_rect, width=16)
        pygame.draw.rect(self.screen, (160, 130, 60), frame_rect.inflate(-16, -16), width=6)
        pygame.draw.rect(self.screen, (218, 165, 32), frame_rect.inflate(-24, -24), width=2)

        # 3. Portrait Canvas Oval / Body & Armor
        inner_rect = frame_rect.inflate(-36, -36)
        pygame.draw.rect(self.screen, (38, 30, 24), inner_rect)

        # Shoulders / Silver Knight Armor & Crimson Sash
        pygame.draw.ellipse(self.screen, (75, 85, 95), (center_x - 180, center_y + 40, 360, 240))
        pygame.draw.ellipse(self.screen, (139, 28, 28), (center_x - 140, center_y + 60, 280, 70))

        # Knight's Plumed Helmet
        pygame.draw.ellipse(self.screen, (120, 130, 140), (center_x - 80, center_y - 200, 160, 100))
        # Plume (Gold/Crimson feather)
        pygame.draw.ellipse(self.screen, (180, 40, 40), (center_x - 30, center_y - 240, 60, 70))
        pygame.draw.ellipse(self.screen, (218, 165, 32), (center_x - 20, center_y - 230, 40, 45))

        # Face
        head_rect = pygame.Rect(center_x - 70, center_y - 120, 140, 170)
        pygame.draw.ellipse(self.screen, (215, 180, 145), head_rect)

        # Bold Knight Mustache
        pygame.draw.arc(self.screen, (90, 60, 30), (center_x - 55, center_y - 15, 55, 30), 0, 3.14, 5)
        pygame.draw.arc(self.screen, (90, 60, 30), (center_x, center_y - 15, 55, 30), 0, 3.14, 5)

        # Eyes (Open or Closed)
        if is_eyes_closed:
            # Curved lines for closed eyelids
            pygame.draw.arc(self.screen, (60, 40, 25), (center_x - 45, center_y - 65, 30, 15), 3.14, 6.28, 3)
            pygame.draw.arc(self.screen, (60, 40, 25), (center_x + 15, center_y - 65, 30, 15), 3.14, 6.28, 3)
        else:
            # Whites & pupils
            pygame.draw.ellipse(self.screen, (245, 245, 240), (center_x - 45, center_y - 70, 30, 18))
            pygame.draw.ellipse(self.screen, (245, 245, 240), (center_x + 15, center_y - 70, 30, 18))
            # Iris
            pygame.draw.circle(self.screen, (60, 100, 130), (center_x - 30, center_y - 61), 7)
            pygame.draw.circle(self.screen, (60, 100, 130), (center_x + 30, center_y - 61), 7)
            # Pupil + highlight
            pygame.draw.circle(self.screen, (10, 10, 10), (center_x - 30, center_y - 61), 4)
            pygame.draw.circle(self.screen, (10, 10, 10), (center_x + 30, center_y - 61), 4)
            pygame.draw.circle(self.screen, (255, 255, 255), (center_x - 32, center_y - 63), 2)
            pygame.draw.circle(self.screen, (255, 255, 255), (center_x + 28, center_y - 63), 2)

        # Eyebrows (Proud knightly arch)
        pygame.draw.arc(self.screen, (80, 50, 25), (center_x - 50, center_y - 85, 40, 20), 0, 3.14, 3)
        pygame.draw.arc(self.screen, (80, 50, 25), (center_x + 10, center_y - 85, 40, 20), 0, 3.14, 3)

        # Mouth (Based on mouth_index: 1=Closed, 2=Partial, 3=Wide)
        mouth_y = center_y + 12
        if mouth_index == 1:
            # Closed line
            pygame.draw.line(self.screen, (120, 50, 45), (center_x - 22, mouth_y), (center_x + 22, mouth_y), 3)
        elif mouth_index == 2:
            # Partial Open
            pygame.draw.ellipse(self.screen, (80, 25, 25), (center_x - 24, mouth_y - 6, 48, 16))
            pygame.draw.ellipse(self.screen, (240, 240, 240), (center_x - 14, mouth_y - 5, 28, 6))  # Teeth
        else:
            # Wide Open (Loud utterance)
            pygame.draw.ellipse(self.screen, (60, 15, 15), (center_x - 28, mouth_y - 10, 56, 26))
            pygame.draw.ellipse(self.screen, (240, 240, 240), (center_x - 18, mouth_y - 8, 36, 8))
            pygame.draw.ellipse(self.screen, (160, 50, 50), (center_x - 12, mouth_y + 4, 24, 10))  # Tongue

    def render(self) -> None:
        """Main frame render call."""
        is_blinking = self.blink_controller.update()

        # Render layered sprite or procedural portrait
        self.draw_fallback_portrait(is_blinking, self.current_mouth_index)

        # Subtitle overlay
        w, h = self.screen.get_size()
        if self.subtitle_text:
            text_surf = self.font.render(f"« {self.subtitle_text} »", True, (245, 230, 190))
            bg_rect = text_surf.get_rect(center=(w // 2, h - 80))
            pad_rect = bg_rect.inflate(30, 16)
            pygame.draw.rect(self.screen, (20, 16, 12), pad_rect, border_radius=8)
            pygame.draw.rect(self.screen, (160, 130, 60), pad_rect, width=2, border_radius=8)
            self.screen.blit(text_surf, bg_rect)

        # Debug HUD
        if self.show_debug_hud:
            hud_text = f"STATE: {self.current_state.value} | MOUTH: {self.current_mouth_index} | AMP: {self.audio_amplitude:.2f}"
            hud_surf = self.hud_font.render(hud_text, True, (218, 165, 32))
            self.screen.blit(hud_surf, (55, 55))

        pygame.display.flip()
        self.clock.tick(self.fps)

    def cleanup(self) -> None:
        pygame.quit()
