"""
hardware/display.py — Animated face shown on the Pi-connected IPS display.

Uses pygame for hardware-accelerated 2D rendering.
States: idle, listening, speaking, thinking, happy, sleeping, focus

Threading model
---------------
pygame's SDL2 backend requires that ALL display operations (init, event pump,
flip) happen on the **main thread**.  This class therefore does NOT run its
own background thread.  Instead, callers must drive it by calling tick() in
their main loop at the desired frame rate.

Quick-start::

    display = Display(width=800, height=480)
    display.start()          # pygame.init + window creation, main thread only
    try:
        while running:
            display.tick()   # draw one frame + pump events, call every ~33 ms
    finally:
        display.stop()

set_state() and show_text() remain fully thread-safe and may be called from
any thread (camera loop, poll loop, etc.).
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
    Animated face display driven by the caller's main loop via tick().

    Thread-safe: set_state() / show_text() may be called from any thread.
    The tick() / start() / stop() methods MUST be called from the main thread.
    """

    def __init__(self, width: int = WIDTH, height: int = HEIGHT, fullscreen: bool = False):
        self.width = width
        self.height = height
        self._lock = threading.Lock()
        self._state = "idle"
        self._overlay: Optional[str] = None
        self._overlay_timer: Optional[threading.Timer] = None
        self._animation_time = 0.0
        self._blink_timer = 0.0
        self._mouth_open = 0.0
        self._last_tick = time.monotonic()
        self._running = False

        self.screen: Optional[pygame.Surface] = None
        self.clock: Optional[pygame.time.Clock] = None
        self.font: Optional[pygame.font.Font] = None
        self.small_font: Optional[pygame.font.Font] = None
        self._fullscreen = fullscreen

    # ------------------------------------------------------------------
    # Lifecycle — MAIN THREAD ONLY
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise pygame and open the window.  Must be called on the main thread."""
        pygame.init()
        pygame.mouse.set_visible(False)

        flags = pygame.FULLSCREEN if self._fullscreen else 0
        try:
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
        except pygame.error as exc:
            logger.error("Failed to set display mode %dx%d: %s", self.width, self.height, exc)
            raise

        pygame.display.set_caption("Table Tot")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 36, bold=True)
        self.small_font = pygame.font.SysFont("Arial", 24)
        self._running = True
        self._last_tick = time.monotonic()
        logger.info("Display started (%dx%d, fullscreen=%s)", self.width, self.height, self._fullscreen)

    def tick(self) -> bool:
        """
        Render one frame and pump the SDL event queue.

        Returns False if the window was closed (caller should stop the loop),
        True otherwise.

        Call this every ~33 ms (30 fps) from the main thread.
        """
        if not self._running or self.screen is None:
            return False

        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self._animation_time += dt
        self._blink_timer += dt

        # Pump SDL events — mandatory on Linux/SDL2 to keep the window alive.
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                self._running = False
                return False

        with self._lock:
            state = self._state
            overlay = self._overlay

        self._draw_frame(state, overlay, dt)
        pygame.display.flip()

        if self.clock:
            self.clock.tick(FPS)

        return True

    def stop(self) -> None:
        """Clean up pygame.  Must be called on the main thread."""
        self._running = False
        if self._overlay_timer:
            self._overlay_timer.cancel()
        pygame.quit()
        logger.info("Display stopped")

    # ------------------------------------------------------------------
    # Thread-safe state setters — safe to call from any thread
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Change face state: idle, listening, speaking, thinking, happy, sleeping, focus"""
        valid = {"idle", "listening", "speaking", "thinking", "happy", "sleeping", "focus"}
        if state not in valid:
            logger.warning("Invalid display state: %r (valid: %s)", state, valid)
            state = "idle"
        with self._lock:
            self._state = state

    def show_text(self, text: str, duration: Optional[float] = None) -> None:
        """Show overlay text. If duration given, auto-clear after that many seconds."""
        with self._lock:
            self._overlay = text
        if duration:
            if self._overlay_timer:
                self._overlay_timer.cancel()
            self._overlay_timer = threading.Timer(duration, self.clear_text)
            self._overlay_timer.daemon = True
            self._overlay_timer.start()

    def clear_text(self) -> None:
        with self._lock:
            self._overlay = None
            self._overlay_timer = None

    @property
    def current_state(self) -> str:
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # Rendering (all called inside tick(), main thread)
    # ------------------------------------------------------------------

    def _draw_frame(self, state: str, overlay: Optional[str], dt: float) -> None:
        assert self.screen is not None
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
        assert self.screen is not None
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
        assert self.screen is not None
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
        assert self.screen is not None
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
        assert self.screen is not None and self.font is not None
        box_height = 100
        box_y = self.height - box_height
        s = pygame.Surface((self.width, box_height), pygame.SRCALPHA)
        s.fill((0, 0, 0, 180))
        self.screen.blit(s, (0, box_y))

        words = text.split()
        lines = []
        current_line: list[str] = []
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
