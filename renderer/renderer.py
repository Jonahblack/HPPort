"""
Pygame Renderer for the Harry Potter Talking Portrait.
Renders layered 2D animation (base, eyes_closed, mouth_1, mouth_2, mouth_3) with
responsive state visualizers, dialogue overlays, and latency performance counters.
"""

import logging
import os
from pathlib import Path
import time
from typing import Callable, Dict, Optional, Tuple

from renderer.animation import AnimationController, MouthFrame
from state_machine import State

logger = logging.getLogger(__name__)


class PortraitRenderer:
    """Non-blocking Pygame renderer displaying the animated portrait and status HUD."""

    def __init__(
        self,
        width: int = 1024,
        height: int = 768,
        fullscreen: bool = False,
        fps: int = 60,
        assets_dir: str = "assets",
        animator: Optional[AnimationController] = None,
    ):
        self.width = width
        self.height = height
        self.fullscreen = fullscreen
        self.fps = fps
        self.assets_dir = Path(assets_dir)
        self.animator = animator or AnimationController()

        self.running = False
        self.screen = None
        self.clock = None
        self.font = None
        self.status_font = None

        # Layers
        self.surf_base = None
        self.surf_eyes_closed = None
        self.surf_mouth_1 = None
        self.surf_mouth_2 = None
        self.surf_mouth_3 = None

        self.current_state: State = State.IDLE
        self.status_message: str = "Waiting for visitor..."
        self.latency_stats: Dict[str, str] = {}

    def init_display(self) -> bool:
        """Initialize Pygame display subsystem."""
        try:
            import pygame
            pygame.init()
            pygame.font.init()

            flags = pygame.FULLSCREEN if self.fullscreen else 0
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
            pygame.display.set_caption("Harry Potter Talking Portrait (Gemma 4)")
            self.clock = pygame.time.Clock()

            try:
                self.font = pygame.font.SysFont("Georgia", 24)
                self.status_font = pygame.font.SysFont("Courier", 16)
            except Exception:
                self.font = pygame.font.Font(None, 24)
                self.status_font = pygame.font.Font(None, 18)

            self._load_assets()
            self.running = True
            logger.info("Pygame renderer initialized (%dx%d, fullscreen=%s)", self.width, self.height, self.fullscreen)
            return True
        except Exception as e:
            logger.error("Failed to initialize Pygame display: %s", e)
            return False

    def _create_synthetic_layer(self, name: str, size: Tuple[int, int]):
        """Generate high-fidelity portrait layers matching the reference photo with glasses, beard, and overlays."""
        import pygame
        surf = pygame.Surface(size, pygame.SRCALPHA)
        w, h = size
        cx, cy = w // 2, h // 2

        # Color palette based on user reference
        skin_base = (220, 185, 160)
        skin_shadow = (190, 150, 125)
        skin_highlight = (235, 205, 180)
        hair_brown = (70, 45, 30)
        beard_brown = (95, 65, 45)
        glasses_black = (25, 25, 28)
        shirt_dark = (40, 44, 48)
        wood_panel = (130, 85, 50)
        wood_line = (90, 55, 30)

        if name == "base":
            # 1. Background - Wooden Cabinet / Wall
            surf.fill(wood_panel)
            # Wood grain / panel lines
            pygame.draw.line(surf, wood_line, (cx - 160, 0), (cx - 160, h), 4)
            pygame.draw.line(surf, wood_line, (cx + 160, 0), (cx + 160, h), 4)
            pygame.draw.rect(surf, (160, 110, 65), (0, 0, w, 24))

            # 2. Shirt / Shoulders
            pygame.draw.ellipse(surf, shirt_dark, (cx - 220, cy + 120, 440, 260))
            pygame.draw.polygon(surf, (30, 34, 38), [(cx, cy + 150), (cx - 50, cy + 220), (cx + 50, cy + 220)])  # Placket
            pygame.draw.polygon(surf, (50, 55, 60), [(cx - 70, cy + 130), (cx - 20, cy + 160), (cx - 50, cy + 180)])  # Collar L
            pygame.draw.polygon(surf, (50, 55, 60), [(cx + 70, cy + 130), (cx + 20, cy + 160), (cx + 50, cy + 180)])  # Collar R

            # 3. Neck
            pygame.draw.rect(surf, skin_shadow, (cx - 45, cy + 60, 90, 80))

            # 4. Hair Back & Ears
            pygame.draw.ellipse(surf, hair_brown, (cx - 110, cy - 170, 220, 220))
            pygame.draw.ellipse(surf, skin_base, (cx - 105, cy - 40, 26, 45))  # Left Ear
            pygame.draw.ellipse(surf, skin_base, (cx + 79, cy - 40, 26, 45))   # Right Ear

            # 5. Face Base
            pygame.draw.ellipse(surf, skin_base, (cx - 90, cy - 140, 180, 220))

            # 6. Forehead & Cheeks shading
            pygame.draw.ellipse(surf, skin_highlight, (cx - 50, cy - 110, 100, 50))

            # 7. Eyes (Open)
            # Sockets
            pygame.draw.ellipse(surf, (250, 248, 245), (cx - 65, cy - 48, 42, 20))
            pygame.draw.ellipse(surf, (250, 248, 245), (cx + 23, cy - 48, 42, 20))
            # Irises (Hazel/Blue-Grey)
            pygame.draw.circle(surf, (75, 95, 110), (cx - 44, cy - 38), 9)
            pygame.draw.circle(surf, (75, 95, 110), (cx + 44, cy - 38), 9)
            # Pupils
            pygame.draw.circle(surf, (15, 15, 18), (cx - 44, cy - 38), 4)
            pygame.draw.circle(surf, (15, 15, 18), (cx + 44, cy - 38), 4)
            # Catchlights
            pygame.draw.circle(surf, (255, 255, 255), (cx - 46, cy - 40), 2)
            pygame.draw.circle(surf, (255, 255, 255), (cx + 42, cy - 40), 2)

            # 8. Eyebrows
            pygame.draw.arc(surf, hair_brown, (cx - 72, cy - 70, 52, 24), 0.2, 2.9, 4)
            pygame.draw.arc(surf, hair_brown, (cx + 20, cy - 70, 52, 24), 0.2, 2.9, 4)

            # 9. Nose
            pygame.draw.polygon(surf, skin_shadow, [(cx, cy - 42), (cx - 10, cy + 5), (cx + 10, cy + 5)])
            pygame.draw.ellipse(surf, skin_highlight, (cx - 7, cy - 35, 14, 38))
            pygame.draw.circle(surf, skin_shadow, (cx - 11, cy + 4), 5)
            pygame.draw.circle(surf, skin_shadow, (cx + 11, cy + 4), 5)

            # 10. Hair Front / Parting
            pygame.draw.arc(surf, hair_brown, (cx - 95, cy - 165, 190, 90), 0.1, 3.0, 18)

            # 11. Glasses Frame (Black Rectangular)
            # Left Rim
            pygame.draw.rect(surf, glasses_black, (cx - 76, cy - 58, 62, 38), 4, border_radius=6)
            # Right Rim
            pygame.draw.rect(surf, glasses_black, (cx + 14, cy - 58, 62, 38), 4, border_radius=6)
            # Bridge
            pygame.draw.line(surf, glasses_black, (cx - 14, cy - 42), (cx + 14, cy - 42), 3)
            # Temples
            pygame.draw.line(surf, glasses_black, (cx - 76, cy - 44), (cx - 96, cy - 42), 3)
            pygame.draw.line(surf, glasses_black, (cx + 76, cy - 44), (cx + 96, cy - 42), 3)
            # Glass Reflection Highlight
            pygame.draw.line(surf, (255, 255, 255, 70), (cx - 65, cy - 52), (cx - 35, cy - 26), 2)
            pygame.draw.line(surf, (255, 255, 255, 70), (cx + 25, cy - 52), (cx + 55, cy - 26), 2)

            # 12. Beard & Mustache (Base Neutral)
            # Mustache
            pygame.draw.ellipse(surf, beard_brown, (cx - 32, cy + 12, 64, 18))
            # Beard along jaw
            pygame.draw.arc(surf, beard_brown, (cx - 75, cy - 10, 150, 110), 3.4, 6.0, 22)
            pygame.draw.ellipse(surf, beard_brown, (cx - 38, cy + 50, 76, 38))
            # Closed mouth line
            pygame.draw.line(surf, (135, 65, 65), (cx - 18, cy + 24), (cx + 18, cy + 24), 3)

        elif name == "eyes_closed":
            # Overlay: Transparent with closed eyelids & glasses
            surf.fill((0, 0, 0, 0))

            # Eyelid skin covering eye area
            pygame.draw.ellipse(surf, skin_base, (cx - 70, cy - 54, 52, 30))
            pygame.draw.ellipse(surf, skin_base, (cx + 18, cy - 54, 52, 30))
            # Eyelash crease line
            pygame.draw.arc(surf, (90, 60, 45), (cx - 64, cy - 46, 40, 14), 3.14, 6.28, 3)
            pygame.draw.arc(surf, (90, 60, 45), (cx + 24, cy - 46, 40, 14), 3.14, 6.28, 3)

            # Glasses over closed eyes
            pygame.draw.rect(surf, glasses_black, (cx - 76, cy - 58, 62, 38), 4, border_radius=6)
            pygame.draw.rect(surf, glasses_black, (cx + 14, cy - 58, 62, 38), 4, border_radius=6)
            pygame.draw.line(surf, glasses_black, (cx - 14, cy - 42), (cx + 14, cy - 42), 3)
            # Glass subtle glint
            pygame.draw.line(surf, (255, 255, 255, 80), (cx - 65, cy - 52), (cx - 35, cy - 26), 2)
            pygame.draw.line(surf, (255, 255, 255, 80), (cx + 25, cy - 52), (cx + 55, cy - 26), 2)

        elif name == "mouth_1":
            # Overlay: Transparent with Mouth 1 (Closed) + Mustache + Beard
            surf.fill((0, 0, 0, 0))
            # Mustache
            pygame.draw.ellipse(surf, beard_brown, (cx - 34, cy + 10, 68, 20))
            # Closed lip line
            pygame.draw.ellipse(surf, (150, 85, 80), (cx - 20, cy + 22, 40, 8))
            pygame.draw.line(surf, (110, 50, 50), (cx - 18, cy + 26), (cx + 18, cy + 26), 2)
            # Chin beard
            pygame.draw.ellipse(surf, beard_brown, (cx - 40, cy + 46, 80, 42))

        elif name == "mouth_2":
            # Overlay: Transparent with Mouth 2 (Slightly Open)
            surf.fill((0, 0, 0, 0))
            # Mustache
            pygame.draw.ellipse(surf, beard_brown, (cx - 34, cy + 10, 68, 20))
            # Mouth aperture (Slightly open, teeth visible)
            pygame.draw.ellipse(surf, (60, 20, 20), (cx - 20, cy + 22, 40, 16))
            # Upper teeth
            pygame.draw.rect(surf, (245, 245, 245), (cx - 12, cy + 23, 24, 5), border_radius=2)
            # Lower lip
            pygame.draw.arc(surf, (160, 90, 85), (cx - 18, cy + 24, 36, 16), 3.2, 6.2, 3)
            # Chin beard
            pygame.draw.ellipse(surf, beard_brown, (cx - 40, cy + 46, 80, 42))

        elif name == "mouth_3":
            # Overlay: Transparent with Mouth 3 (Open)
            surf.fill((0, 0, 0, 0))
            # Mustache
            pygame.draw.ellipse(surf, beard_brown, (cx - 34, cy + 8, 68, 20))
            # Deep oral cavity
            pygame.draw.ellipse(surf, (40, 12, 14), (cx - 22, cy + 20, 44, 26))
            # Upper teeth
            pygame.draw.rect(surf, (245, 245, 245), (cx - 14, cy + 21, 28, 6), border_radius=2)
            # Tongue
            pygame.draw.ellipse(surf, (160, 55, 65), (cx - 10, cy + 34, 20, 10))
            # Lower teeth line
            pygame.draw.rect(surf, (235, 235, 235), (cx - 10, cy + 38, 20, 4), border_radius=1)
            # Lower lip
            pygame.draw.arc(surf, (155, 80, 75), (cx - 20, cy + 28, 40, 20), 3.2, 6.2, 3)
            # Chin beard
            pygame.draw.ellipse(surf, beard_brown, (cx - 40, cy + 50, 80, 44))

        return surf

    def _load_assets(self) -> None:
        """Load asset PNG files or create synthetic fallback layers."""
        import pygame
        size = (self.width, self.height)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        layers = {
            "base": ("base.png", "_create_synthetic_layer"),
            "eyes_closed": ("eyes_closed.png", "_create_synthetic_layer"),
            "mouth_1": ("mouth_1.png", "_create_synthetic_layer"),
            "mouth_2": ("mouth_2.png", "_create_synthetic_layer"),
            "mouth_3": ("mouth_3.png", "_create_synthetic_layer"),
        }

        for key, (filename, _) in layers.items():
            path = self.assets_dir / filename
            if path.exists():
                try:
                    surf = pygame.image.load(str(path)).convert_alpha()
                    surf = pygame.transform.smoothscale(surf, size)
                    setattr(self, f"surf_{key}", surf)
                    logger.info("Loaded custom asset: %s", path)
                    continue
                except Exception as e:
                    logger.warning("Could not load %s: %s. Generating synthetic layer.", path, e)

            # Generate synthetic placeholder
            surf = self._create_synthetic_layer(key, size)
            setattr(self, f"surf_{key}", surf)
            # Save synthetic asset to disk for convenience
            try:
                pygame.image.save(surf, str(path))
            except Exception:
                pass

    def handle_events(
        self,
        on_space_pressed: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_text_injected: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Process keyboard & window events without blocking."""
        import pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                if on_quit:
                    on_quit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    self.running = False
                    if on_quit:
                        on_quit()
                elif event.key == pygame.K_SPACE:
                    if on_space_pressed:
                        on_space_pressed()
                elif event.key == pygame.K_t:
                    # Injected sample dialogue shortcut for quick desktop testing
                    if on_text_injected:
                        on_text_injected("Tell me about Hogwarts castle!")

    def render(self, state: State, status_text: str = "", latency_metrics: Optional[Dict[str, str]] = None) -> None:
        """Render a single frame."""
        if not self.screen:
            return

        import pygame
        self.current_state = state
        if status_text:
            self.status_message = status_text
        if latency_metrics:
            self.latency_stats = latency_metrics

        # Update animation logic
        self.animator.update()

        # 1. Base portrait layer
        if self.surf_base:
            self.screen.blit(self.surf_base, (0, 0))

        # 2. Eye state (eyes_closed overlay if blinking)
        if self.animator.eyes_closed and self.surf_eyes_closed:
            self.screen.blit(self.surf_eyes_closed, (0, 0))

        # 3. Mouth state (mouth_1 / mouth_2 / mouth_3)
        mouth_frame = self.animator.mouth_frame
        if mouth_frame == MouthFrame.OPEN and self.surf_mouth_3:
            self.screen.blit(self.surf_mouth_3, (0, 0))
        elif mouth_frame == MouthFrame.PARTIAL and self.surf_mouth_2:
            self.screen.blit(self.surf_mouth_2, (0, 0))
        elif self.surf_mouth_1:
            self.screen.blit(self.surf_mouth_1, (0, 0))

        # 4. State HUD overlay
        self._render_hud()

        pygame.display.flip()
        if self.clock:
            self.clock.tick(self.fps)

    def _render_hud(self) -> None:
        import pygame
        # Status pill badge at bottom left
        state_colors = {
            State.IDLE: (90, 90, 90),
            State.WAKE_PENDING: (200, 160, 40),
            State.GREETING: (60, 160, 220),
            State.LISTENING: (50, 190, 90),
            State.THINKING: (170, 80, 220),
            State.SPEAKING: (220, 120, 50),
            State.COOLDOWN: (140, 70, 70),
        }
        color = state_colors.get(self.current_state, (100, 100, 100))

        # Draw semi-transparent status bar at bottom
        hud_rect = pygame.Rect(20, self.height - 70, self.width - 40, 50)
        hud_surface = pygame.Surface((hud_rect.width, hud_rect.height), pygame.SRCALPHA)
        hud_surface.fill((15, 12, 10, 210))
        pygame.draw.rect(hud_surface, (140, 110, 60), (0, 0, hud_rect.width, hud_rect.height), 1, border_radius=8)
        self.screen.blit(hud_surface, (hud_rect.x, hud_rect.y))

        # State indicator circle
        pygame.draw.circle(self.screen, color, (hud_rect.x + 25, hud_rect.y + 25), 10)

        # State name & message
        if self.font:
            txt_state = self.font.render(f"{self.current_state.name}:", True, (240, 220, 180))
            self.screen.blit(txt_state, (hud_rect.x + 45, hud_rect.y + 12))

            msg = self.status_message
            if len(msg) > 60:
                msg = msg[:57] + "..."
            txt_msg = self.font.render(msg, True, (230, 230, 230))
            self.screen.blit(txt_msg, (hud_rect.x + 45 + txt_state.get_width() + 10, hud_rect.y + 12))

        # Latency statistics in top right
        if self.latency_stats and self.status_font:
            top_y = 25
            for k, v in self.latency_stats.items():
                txt_stat = self.status_font.render(f"{k}: {v}", True, (220, 200, 140))
                bg_rect = pygame.Rect(self.width - txt_stat.get_width() - 40, top_y - 2, txt_stat.get_width() + 16, 22)
                bg_s = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
                bg_s.fill((10, 10, 10, 180))
                self.screen.blit(bg_s, (bg_rect.x, bg_rect.y))
                self.screen.blit(txt_stat, (self.width - txt_stat.get_width() - 32, top_y))
                top_y += 26

    def close(self) -> None:
        """Clean shutdown."""
        self.running = False
        try:
            import pygame
            pygame.quit()
        except Exception:
            pass
