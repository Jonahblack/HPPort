import math
import os
import random
import threading
import time
from dataclasses import dataclass

import pygame

from state_machine import PortraitState


@dataclass
class RenderState:
    portrait_state: PortraitState = PortraitState.IDLE
    mouth_level: float = 0.0
    camera_mode: str = "disabled"
    camera_available: bool = False
    status_text: str = ""


class PortraitRenderer:
    def __init__(self, config: dict):
        self.config = config
        self.width = int(config.get("width", 800))
        self.height = int(config.get("height", 480))
        self.fps = int(config.get("fps", 30))
        self.window_title = str(config.get("window_title", "Talking Portrait"))
        self.state = RenderState()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._quit_requested = False
        self._demo_trigger_requested = False
        self._next_blink_at = time.monotonic() + random.uniform(2.2, 4.5)
        self._blink_until = 0.0
        self._eye_offset = 0.0
        self._eye_velocity = 0.0

    def start(self) -> None:
        if self.config.get("headless", False):
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, name="portrait-renderer", daemon=True)
        self._thread.start()

    def update(self, portrait_state: PortraitState, mouth_level: float = None, camera_mode: str = None, camera_available: bool = None, status_text: str = None) -> None:
        with self._lock:
            self.state.portrait_state = portrait_state
            if mouth_level is not None:
                self.state.mouth_level = max(0.0, min(1.0, mouth_level))
            if camera_mode is not None:
                self.state.camera_mode = camera_mode
            if camera_available is not None:
                self.state.camera_available = camera_available
            if status_text is not None:
                self.state.status_text = status_text

    def consume_demo_trigger(self) -> bool:
        with self._lock:
            pending = self._demo_trigger_requested
            self._demo_trigger_requested = False
            return pending

    def quit_requested(self) -> bool:
        return self._quit_requested

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run_loop(self) -> None:
        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(self.window_title)
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("georgia", 24)
        small_font = pygame.font.SysFont("georgia", 18)

        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._quit_requested = True
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._quit_requested = True
                        self._running = False
                    elif event.key == pygame.K_SPACE:
                        with self._lock:
                            self._demo_trigger_requested = True

            with self._lock:
                state = RenderState(**self.state.__dict__)

            now = time.monotonic()
            if now >= self._next_blink_at:
                self._blink_until = now + 0.14
                self._next_blink_at = now + random.uniform(2.2, 5.2)
            blinking = now <= self._blink_until

            target_eye = math.sin(now * 0.55) * 4.0
            self._eye_velocity += (target_eye - self._eye_offset) * 0.08
            self._eye_velocity *= 0.85
            self._eye_offset += self._eye_velocity

            bg = tuple(self.config.get("background_color", [18, 21, 28]))
            accent = tuple(self.config.get("accent_color", [198, 134, 73]))
            eye = tuple(self.config.get("eye_color", [248, 244, 236]))
            pupil = tuple(self.config.get("pupil_color", [32, 28, 27]))
            mouth = tuple(self.config.get("mouth_color", [126, 48, 43]))
            text_color = tuple(self.config.get("status_text_color", [232, 228, 220]))

            screen.fill(bg)
            pygame.draw.rect(screen, (36, 40, 52), pygame.Rect(48, 48, self.width - 96, self.height - 96), border_radius=30)
            pygame.draw.rect(screen, accent, pygame.Rect(58, 58, self.width - 116, self.height - 116), width=5, border_radius=28)

            portrait_rect = pygame.Rect(self.width // 2 - 140, 100, 280, 260)
            pygame.draw.ellipse(screen, (214, 193, 167), portrait_rect)
            pygame.draw.ellipse(screen, (74, 57, 44), portrait_rect, width=6)

            eye_y = portrait_rect.y + 95
            left_eye_x = portrait_rect.centerx - 52
            right_eye_x = portrait_rect.centerx + 52
            if blinking:
                pygame.draw.line(screen, pupil, (left_eye_x - 22, eye_y), (left_eye_x + 22, eye_y), 4)
                pygame.draw.line(screen, pupil, (right_eye_x - 22, eye_y), (right_eye_x + 22, eye_y), 4)
            else:
                for eye_x in (left_eye_x, right_eye_x):
                    pygame.draw.ellipse(screen, eye, pygame.Rect(eye_x - 28, eye_y - 18, 56, 36))
                    pygame.draw.circle(screen, pupil, (int(eye_x + self._eye_offset), eye_y + 2), 10)

            mouth_width = 84
            mouth_height = 12 + int(36 * state.mouth_level)
            mouth_rect = pygame.Rect(0, 0, mouth_width, mouth_height)
            mouth_rect.center = (portrait_rect.centerx, portrait_rect.y + 180)
            pygame.draw.ellipse(screen, mouth, mouth_rect)
            if state.portrait_state != PortraitState.SPEAKING and state.mouth_level < 0.1:
                pygame.draw.line(screen, (70, 32, 30), (mouth_rect.left + 10, mouth_rect.centery), (mouth_rect.right - 10, mouth_rect.centery), 3)

            glow_radius = 10 if state.portrait_state == PortraitState.IDLE else 18
            pygame.draw.circle(screen, accent, (portrait_rect.centerx, portrait_rect.y + 228), glow_radius, width=2)

            screen.blit(font.render(state.portrait_state.value, True, text_color), (60, 22))
            camera_text = f"Camera: {state.camera_mode}" if state.camera_available else f"Camera: {state.camera_mode or 'offline'}"
            screen.blit(small_font.render(camera_text, True, text_color), (60, self.height - 68))
            screen.blit(small_font.render("Space: demo wake   Esc: quit", True, text_color), (60, self.height - 42))

            if state.status_text:
                screen.blit(small_font.render(state.status_text[:72], True, text_color), (60, self.height - 94))

            pygame.display.flip()
            clock.tick(self.fps)

        pygame.quit()
