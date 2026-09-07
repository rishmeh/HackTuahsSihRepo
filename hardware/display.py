"""
hardware/display.py — Animated face shown on the Pi-connected IPS display.

Uses pygame for hardware-accelerated 2D rendering.
States: idle, listening, speaking, thinking, happy, sleeping, focus
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Optional

import pygame

logger = logging.getLogger(__name__)

WIDTH = 800
HEIGHT = 480
FPS = 30

BLACK = (20, 20, 20)
WHITE = (240, 240, 240)
AMBER = (255, 180, 0)
GREEN = (0, 200, 100)
BLUE = (0, 150, 255)
PINK = (255, 100, 150)

CENTER_X = WIDTH // 2
CENTER_Y = HEIGHT // 2
EYE_Y = CENTER_Y - 30
EYE_SPACING = 80
EYE_WIDTH = 50
EYE_HEIGHT = 60
MOUTH_Y = CENTER_Y + 50


class Display:
    """
    Animated face display running in a background thread.
    Thread-safe: call set_state() from any thread.
    """

    def __init__(self, width: int = WIDTH, height: int = HEIGHT, fullscreen: bool = False):
        self.width = width
        self.height = height
        self._running = False
        self._lock = threading.Lock()
        self._state = "idle"
        self._overlay: Optional[str] = None
        self._overlay_timer: Optional[threading.Timer] = None
        self._animation_time = 0.0
        self._blink_timer = 0.0
        self._mouth_open = 0.0
        self._thread: Optional[threading.Thread] = None

        pygame.init()
        pygame.mouse.set_visible(False)

        flags = pygame.FULLSCREEN if fullscreen else 0
        try:
            self.screen = pygame.display.set_mode((width, height), flags)
        except pygame.error as exc:
            logger.error("Failed to set display mode %dx%d: %s", width, height, exc)
            raise

        pygame.display.set_caption("Table Tot")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 36, bold=True)
        self.small_font = pygame.font.SysFont("Arial", 24)

    def start(self):
        """Start the display loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Display started")

    def stop(self):
        """Stop the display loop and cleanup pygame."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        pygame.quit()
        logger.info("Display stopped")

    def set_state(self, state: str):
        """Change face state: idle, listening, speaking, thinking, happy, sleeping, focus"""
        valid = {"idle", "listening", "speaking", "thinking", "happy", "sleeping", "focus"}
        if state not in valid:
            logger.warning("Invalid display state: %r (valid: %s)", state, valid)
            state = "idle"
        with self._lock:
            self._state = state

    def show_text(self, text: str, duration: Optional[float] = None):
        """Show overlay text. If duration given, auto-clear after that many seconds."""
        with self._lock:
            self._overlay = text
        if duration:
            if self._overlay_timer:
                self._overlay_timer.cancel()
            self._overlay_timer = threading.Timer(duration, self.clear_text)
            self._overlay_timer.daemon = True
            self._overlay_timer.start()

    def clear_text(self):
        with self._lock:
            self._overlay = None
            self._overlay_timer = None

    @property
    def current_state(self) -> str:
        with self._lock:
            return self._state

    def _loop(self):
        """Main display loop."""
        while self._running:
            dt = self.clock.tick(FPS) / 1000.0
            self._animation_time += dt
            self._blink_timer += dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False

            with self._lock:
                state = self._state
                overlay = self._overlay
                self._draw_frame(state, overlay, dt)

            pygame.display.flip()

    def _draw_frame(self, state: str, overlay: Optional[str], dt: float):
        self.screen.fill(BLACK)

        blink_cycle = self._blink_timer % 4.0
        eyes_closed = blink_cycle < 0.15

        if state == "speaking":
            speak_cycle = self._animation_time * 8.0
            self._mouth_open = 0.5 + 0.5 * abs(math.sin(speak_cycle))
        elif state == "happy":
            self._mouth_open = 0.8
        else:
            self._mouth_open = max(0.0, self._mouth_open - dt * 5.0)

        if state == "sleeping":
            eyes_closed = True

        self._draw_eyes(EYE_Y, EYE_SPACING, EYE_WIDTH, EYE_HEIGHT, eyes_closed, state)
        self._draw_mouth(CENTER_X, MOUTH_Y, state)

        if state in ("thinking", "happy", "listening"):
            self._draw_eyebrows(state)

        if overlay:
            self._draw_overlay(overlay)

    def _draw_eyes(self, y, spacing, width, height, closed, state):
        left_x = CENTER_X - spacing
        right_x = CENTER_X + spacing

        eye_color = WHITE
        if state == "listening":
            eye_color = BLUE
        elif state == "happy":
            eye_color = GREEN
        elif state == "thinking":
            eye_color = AMBER

        for x in (left_x, right_x):
            if closed:
                pygame.draw.line(self.screen, WHITE,
                    (x - width // 2, y), (x + width // 2, y), 4)
            else:
                rect = pygame.Rect(x - width // 2, y - height // 2, width, height)
                pygame.draw.ellipse(self.screen, eye_color, rect)

                pupil_radius = height // 5
                pygame.draw.circle(self.screen, BLACK, (x, y), pupil_radius)
                highlight_pos = (x - pupil_radius // 3, y - pupil_radius // 3)
                pygame.draw.circle(self.screen, WHITE, highlight_pos, pupil_radius // 3)

    def _draw_mouth(self, x, y, state):
        mouth_width = 80

        if state == "happy":
            pygame.draw.arc(self.screen, WHITE,
                (x - mouth_width // 2, y - 20, mouth_width, 40), 0.2, 3.0, 5)
        elif state == "speaking":
            open_amount = int(self._mouth_open * 25)
            pygame.draw.ellipse(self.screen, WHITE,
                (x - mouth_width // 2, y - open_amount // 2, mouth_width, open_amount + 10))
        elif state == "thinking":
            pygame.draw.arc(self.screen, WHITE,
                (x - 20, y - 5, 40, 20), 3.9, 6.0, 3)
        elif state == "listening":
            pygame.draw.arc(self.screen, WHITE,
                (x - 30, y - 10, 60, 30), 0.3, 2.8, 4)
        else:
            pygame.draw.arc(self.screen, WHITE,
                (x - 25, y - 8, 50, 25), 3.9, 6.0, 3)

    def _draw_eyebrows(self, state):
        y = EYE_Y - EYE_HEIGHT // 2 - 15
        left_x = CENTER_X - EYE_SPACING
        right_x = CENTER_X + EYE_SPACING
        brow_width = 40

        if state == "thinking":
            pygame.draw.line(self.screen, AMBER,
                (left_x - brow_width // 2, y - 10), (left_x + brow_width // 2, y + 5), 4)
            pygame.draw.line(self.screen, AMBER,
                (right_x - brow_width // 2, y + 5), (right_x + brow_width // 2, y - 10), 4)
        elif state == "happy":
            pygame.draw.arc(self.screen, GREEN,
                (left_x - brow_width // 2, y - 10, brow_width, 20), 3.5, 6.0, 4)
            pygame.draw.arc(self.screen, GREEN,
                (right_x - brow_width // 2, y - 10, brow_width, 20), 3.5, 6.0, 4)
        elif state == "listening":
            pygame.draw.line(self.screen, BLUE,
                (left_x - brow_width // 2, y), (left_x + brow_width // 2, y), 4)
            pygame.draw.line(self.screen, BLUE,
                (right_x - brow_width // 2, y), (right_x + brow_width // 2, y), 4)

    def _draw_overlay(self, text: str):
        box_height = 100
        box_y = self.height - box_height
        s = pygame.Surface((self.width, box_height), pygame.SRCALPHA)
        s.fill((0, 0, 0, 180))
        self.screen.blit(s, (0, box_y))

        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test = " ".join(current_line + [word])
            if self.font.size(test)[0] < self.width - 40:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))

        y = box_y + 20
        for line in lines[:4]:
            rendered = self.font.render(line, True, WHITE)
            rect = rendered.get_rect(center=(self.width // 2, y))
            self.screen.blit(rendered, rect)
            y += 40
