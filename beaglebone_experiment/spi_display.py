"""beaglebone_experiment/spi_display.py — ST7789 SPI IPS face display for BeagleBone Black.

Drives a bare 4-wire SPI IPS panel (e.g. 240x240 ST7789) through spidev + Pillow.
Exposes the same interface as hardware.display.Display so bridge.py uses it as a
drop-in replacement — the BBB experiment shows the face on the small SPI screen
instead of HDMI.

Wiring (BBB P9 header, SPI0). These pins are chosen because they do NOT collide
with the PRU servo pins P9_29 / P9_31 or HDMI:

  Panel pin | BBB P9 pin | Function
  ----------|------------|----------
  VCC       | P9_3 (3.3 V) or P9_5 (5 V)   — check your panel
  GND       | P9_1                         — ground
  SCL/SCK   | P9_22                        — SPI0_SCLK
  SDA/MOSI  | P9_18                        — SPI0_D1 (data out from BBB)
  RES/RST   | P9_13                        — GPIO (data/command select)
  DC/RS     | P9_15                        — GPIO (P9_12 conflicts with HDMI)
  CS        | P9_17                        — SPI0_CS0 (hardware chip select)
  BL/LED    | P9_14 (GPIO) or tie to VCC  — backlight (optional)
"""

from __future__ import annotations

import logging
import os
import struct
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_WIDTH = 240
DEFAULT_HEIGHT = 240
FPS = 30

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
AMBER = (255, 180, 0)
GREEN = (0, 200, 100)
BLUE = (0, 150, 255)
PINK = (255, 100, 150)

# BBB P9 GPIO numbers (Linux sysfs numbering: bank * 32 + pin_in_bank).
# Chosen to avoid P9_29 (PRU body servo), P9_31 (PRU head servo), and HDMI.
# P9_12 = GPIO 60 is used by HDMI on BBB — use P9_15 instead.
DEFAULT_DC_GPIO = 48   # P9_15 — GPIO1_16
DEFAULT_RST_GPIO = 31  # P9_13 — GPIO0_31
DEFAULT_BL_GPIO = 50   # P9_14 — GPIO1_18

# ST7789 initialization command sequence.
# Each entry: (command_byte, data_bytes_or_None, delay_ms)
_INIT_SEQUENCE = [
    (0x01, None, 150),        # SWRESET
    (0x11, None, 120),        # SLPOUT
    (0x3A, b'\x55', 10),      # COLMOD: 16 bits/pixel (RGB565)
    (0x36, b'\x00', 0),       # MADCTL: portrait, RGB (rotation bits added at runtime)
    (0x21, None, 0),          # INVON (invert colours — many small panels need this)
    (0x13, None, 0),          # NORON
    (0x29, None, 120),        # DISPON
]


def _gpio_sysfs_write(path: str, value: str) -> None:
    with open(path, 'w') as f:
        f.write(value)


class SpiDisplay:
    """ST7789 SPI IPS face display running in a background thread.

    Thread-safe: call set_state() / show_text() from any thread.
    Drop-in replacement for hardware.display.Display.
    """

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fullscreen: bool = True,  # kept for API compat; SPI is always full-screen
        dc_gpio: int = DEFAULT_DC_GPIO,
        rst_gpio: int = DEFAULT_RST_GPIO,
        bl_gpio: int = DEFAULT_BL_GPIO,
        spi_bus: int = 0,
        spi_cs: int = 0,
        spi_speed_hz: int = 40_000_000,
        rotation: int = 0,
        bgr: bool = False,
        col_offset: int = 0,
        row_offset: int = 0,
    ) -> None:
        self.width = width
        self.height = height
        self.rotation = rotation % 360
        self.bgr = bgr
        self._col_offset = col_offset
        self._row_offset = row_offset

        self._dc_gpio = dc_gpio
        self._rst_gpio = rst_gpio
        self._bl_gpio = bl_gpio
        self._spi_bus = spi_bus
        self._spi_cs = spi_cs
        self._spi_speed_hz = spi_speed_hz

        self._running = False
        self._lock = threading.Lock()
        self._state = "idle"
        self._overlay: Optional[str] = None
        self._overlay_timer: Optional[threading.Timer] = None
        self._animation_time = 0.0
        self._blink_timer = 0.0
        self._mouth_open = 0.0
        self._thread: Optional[threading.Thread] = None

        # --- Lazy imports so the module imports cleanly even without spidev/PIL ---
        try:
            import spidev  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "spidev is not installed. On the BBB run: "
                "sudo apt install python3-spidev"
            ) from exc
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Pillow is not installed. On the BBB run: "
                "sudo apt install python3-pil"
            ) from exc

        # --- Verify SPI device exists ---
        self._spi = spidev.SpiDev()
        self._spi.open(self._spi_bus, self._spi_cs)
        self._spi.max_speed_hz = self._spi_speed_hz
        self._spi.mode = 0b00
        self._spi.bits_per_word = 8

        # Store module references for use in other methods
        self._Image = Image
        self._ImageDraw = ImageDraw
        self._ImageFont = ImageFont

        self._setup_gpio()
        self._init_panel()
        self._setup_fonts()

        logger.info(
            "SPI display ready: %dx%d, rotation=%d, DC=%d RST=%d BL=%d, spi=%d.%d @ %d Hz",
            width, height, self.rotation, dc_gpio, rst_gpio, bl_gpio,
            spi_bus, spi_cs, spi_speed_hz,
        )

    # ------------------------------------------------------------------ GPIO / SPI

    @staticmethod
    def _export_gpio(gpio: int) -> None:
        path = f"/sys/class/gpio/gpio{gpio}"
        if not os.path.isdir(path):
            _gpio_sysfs_write("/sys/class/gpio/export", str(gpio))
            # udev / gpio subsystem may take a moment to create the directory
            for _ in range(20):
                if os.path.isdir(path):
                    return
                time.sleep(0.05)
            raise RuntimeError(f"GPIO {gpio} did not appear after export")

    def _setup_gpio(self) -> None:
        for gpio in (self._dc_gpio, self._rst_gpio, self._bl_gpio):
            self._export_gpio(gpio)
            time.sleep(0.05)
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._dc_gpio}/direction", "out")
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._rst_gpio}/direction", "out")
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._bl_gpio}/direction", "out")
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._bl_gpio}/value", "1")  # backlight on

    def _init_panel(self) -> None:
        # Hardware reset
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._rst_gpio}/value", "1")
        time.sleep(0.01)
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._rst_gpio}/value", "0")
        time.sleep(0.01)
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._rst_gpio}/value", "1")
        time.sleep(0.12)

        madctl = {0: 0x00, 90: 0x60, 180: 0xC0, 270: 0xA0}[self.rotation]
        if self.bgr:
            madctl |= 0x08

        for cmd, data, delay in _INIT_SEQUENCE:
            if cmd == 0x36:
                data = bytes([madctl])
            self._send_command(cmd)
            if data:
                self._send_data(data)
            if delay:
                time.sleep(delay / 1000.0)

    def _setup_fonts(self) -> None:
        # Pillow ships a tiny built-in font; try to load something nicer if present.
        size_main = max(10, self.height // 10)
        size_small = max(8, self.height // 14)
        for candidate in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ):
            if os.path.isfile(candidate):
                try:
                    self._font = self._ImageFont.truetype(candidate, size_main)
                    self._small_font = self._ImageFont.truetype(candidate, size_small)
                    return
                except Exception:
                    pass
        self._font = self._ImageFont.load_default()
        self._small_font = self._ImageFont.load_default()

    # --------------------------------------------------------------- low-level SPI

    def _send_command(self, cmd: int) -> None:
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._dc_gpio}/value", "0")
        self._spi.writebytes([cmd & 0xFF])

    def _send_data(self, data) -> None:
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._dc_gpio}/value", "1")
        self._spi.writebytes(list(data) if isinstance(data, (bytes, bytearray)) else [data & 0xFF])

    def _set_full_window(self) -> None:
        """Point the ST7789 write cursor at the entire panel."""
        w, h = self.width, self.height
        # CASET — column (x) range
        self._send_command(0x2A)
        self._send_data(struct.pack(">HH", self._col_offset, self._col_offset + w - 1))
        # RASET — row (y) range
        self._send_command(0x2B)
        self._send_data(struct.pack(">HH", self._row_offset, self._row_offset + h - 1))
        # RAMWR — pixel stream follows
        self._send_command(0x2C)
        _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._dc_gpio}/value", "1")

    @staticmethod
    def _pil_to_rgb565(image) -> bytearray:
        """Convert a Pillow RGB image to a flat RGB565 byte stream."""
        pixels = image.load()
        w, h = image.size
        buf = bytearray(w * h * 2)
        i = 0
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y][:3]
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                buf[i] = rgb565 >> 8
                buf[i + 1] = rgb565 & 0xFF
                i += 2
        return buf

    def _flush(self, image) -> None:
        """Push a full-frame image to the panel."""
        self._set_full_window()
        self._spi.writebytes2(self._pil_to_rgb565(image))

    # --------------------------------------------------------------- public API

    def start(self) -> None:
        """Start the animation loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="bb-spi-display", daemon=True)
        self._thread.start()
        logger.info("SPI display started")

    def stop(self) -> None:
        """Stop the animation loop and release resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        # Backlight off
        try:
            _gpio_sysfs_write(f"/sys/class/gpio/gpio{self._bl_gpio}/value", "0")
        except Exception:
            pass
        try:
            self._spi.close()
        except Exception:
            pass
        logger.info("SPI display stopped")

    def set_state(self, state: str) -> None:
        """Change face state. Valid: idle, listening, speaking, thinking, happy, sleeping, focus."""
        valid = {"idle", "listening", "speaking", "thinking", "happy", "sleeping", "focus"}
        if state not in valid:
            logger.warning("Invalid display state: %r (valid: %s)", state, valid)
            state = "idle"
        with self._lock:
            self._state = state

    def show_text(self, text: str, duration: Optional[float] = None) -> None:
        """Overlay text. If duration given, auto-clear after that many seconds."""
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

    # --------------------------------------------------------------- animation loop

    def _loop(self) -> None:
        frame_duration = 1.0 / FPS
        last_time = time.monotonic()
        while self._running:
            now = time.monotonic()
            dt = now - last_time
            last_time = now
            self._animation_time += dt
            self._blink_timer += dt

            with self._lock:
                state = self._state
                overlay = self._overlay

            image = self._render_frame(state, overlay, dt)
            try:
                self._flush(image)
            except Exception as exc:
                logger.warning("SPI flush failed: %s", exc)
                time.sleep(frame_duration)
                continue

            elapsed = time.monotonic() - last_time
            sleep_time = frame_duration - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # --------------------------------------------------------------- face rendering

    def _render_frame(self, state: str, overlay: Optional[str], dt: float):
        image = self._Image.new("RGB", (self.width, self.height), BLACK)
        draw = self._ImageDraw.Draw(image)

        cx = self.width // 2
        cy = self.height // 2 - 5  # nudge up slightly to leave room for mouth/overlay

        # Scale geometry to panel size. Base design targets a 240x240 canvas.
        scale = self.width / 240.0

        eye_spacing = int(50 * scale)
        eye_w = int(30 * scale)
        eye_h = int(36 * scale)
        mouth_y = int(150 * scale)
        mouth_w = int(80 * scale)
        brow_y_offset = int(35 * scale)
        brow_w = int(40 * scale)
        pupil_r = int(7 * scale)

        # --- blink ---
        blink_cycle = self._blink_timer % 4.0
        eyes_closed = blink_cycle < 0.15

        # --- mouth openness ---
        if state == "speaking":
            speak_cycle = self._animation_time * 8.0
            import math as _math
            self._mouth_open = 0.5 + 0.5 * abs(_math.sin(speak_cycle))
        elif state == "happy":
            self._mouth_open = 0.8
        else:
            self._mouth_open = max(0.0, self._mouth_open - dt * 5.0)

        if state == "sleeping":
            eyes_closed = True

        # --- eye colour ---
        eye_color = WHITE
        if state == "listening":
            eye_color = BLUE
        elif state == "happy":
            eye_color = GREEN
        elif state == "thinking":
            eye_color = AMBER

        self._draw_eyes(draw, cx, cy, eye_spacing, eye_w, eye_h, pupil_r, eyes_closed, eye_color, scale)
        self._draw_mouth(draw, cx, mouth_y, mouth_w, state, scale, self._mouth_open)

        if state in ("thinking", "happy", "listening"):
            self._draw_eyebrows(draw, cx, cy, eye_spacing, brow_w, brow_y_offset, state, scale)

        if overlay:
            self._draw_overlay(draw, overlay)

        return image

    @staticmethod
    def _draw_eyes(draw, cx, cy, spacing, w, h, pupil_r, closed, eye_color, scale):
        left_x = cx - spacing
        right_x = cx + spacing
        lw = max(2, int(4 * scale))

        for x in (left_x, right_x):
            if closed:
                draw.line((x - w // 2, cy, x + w // 2, cy), fill=WHITE, width=lw)
            else:
                draw.ellipse((x - w // 2, cy - h // 2, x + w // 2, cy + h // 2), fill=eye_color)
                draw.ellipse((x - pupil_r, cy - pupil_r, x + pupil_r, cy + pupil_r), fill=BLACK)
                hl_r = max(1, pupil_r // 3)
                draw.ellipse((x - pupil_r // 3 - hl_r, cy - pupil_r // 3 - hl_r,
                              x - pupil_r // 3 + hl_r, cy - pupil_r // 3 + hl_r), fill=WHITE)

    @staticmethod
    def _draw_mouth(draw, x, y, width, state, scale, mouth_open=0.0):
        lw = max(2, int(5 * scale))
        lw_small = max(2, int(3 * scale))
        hw = width // 2

        if state == "happy":
            draw.arc((x - hw, y - int(20 * scale), x + hw, y + int(20 * scale)),
                     start=20, end=160, fill=WHITE, width=lw)
        elif state == "speaking":
            open_amount = max(int(4 * scale), int(mouth_open * int(25 * scale)))
            draw.ellipse((x - hw, y - open_amount // 2, x + hw, y + open_amount + int(4 * scale)),
                         fill=WHITE)
        elif state == "thinking":
            draw.arc((x - int(20 * scale), y - int(5 * scale), x + int(20 * scale), y + int(15 * scale)),
                     start=230, end=360, fill=WHITE, width=lw_small)
        elif state == "listening":
            draw.arc((x - int(30 * scale), y - int(10 * scale), x + int(30 * scale), y + int(20 * scale)),
                     start=20, end=160, fill=WHITE, width=lw)
        else:
            draw.arc((x - int(25 * scale), y - int(8 * scale), x + int(25 * scale), y + int(17 * scale)),
                     start=230, end=360, fill=WHITE, width=lw_small)

    @staticmethod
    def _draw_eyebrows(draw, cx, cy, spacing, bw, y_off, state, scale):
        lw = max(2, int(4 * scale))
        left_x = cx - spacing
        right_x = cx + spacing
        y = cy - y_off

        if state == "thinking":
            draw.line((left_x - bw // 2, y - int(10 * scale), left_x + bw // 2, y + int(5 * scale)),
                      fill=AMBER, width=lw)
            draw.line((right_x - bw // 2, y + int(5 * scale), right_x + bw // 2, y - int(10 * scale)),
                      fill=AMBER, width=lw)
        elif state == "happy":
            draw.arc((left_x - bw // 2, y - int(10 * scale), left_x + bw // 2, y + int(10 * scale)),
                     start=200, end=340, fill=GREEN, width=lw)
            draw.arc((right_x - bw // 2, y - int(10 * scale), right_x + bw // 2, y + int(10 * scale)),
                     start=200, end=340, fill=GREEN, width=lw)
        elif state == "listening":
            draw.line((left_x - bw // 2, y, left_x + bw // 2, y), fill=BLUE, width=lw)
            draw.line((right_x - bw // 2, y, right_x + bw // 2, y), fill=BLUE, width=lw)

    def _draw_overlay(self, draw, text: str) -> None:
        box_height = int(self.height * 0.28)
        box_y = self.height - box_height
        # semi-transparent bar (PIL has no alpha blend without composite; we draw a solid dark rect)
        draw.rectangle((0, box_y, self.width, self.height), fill=(10, 10, 10))

        # Word-wrap
        words = text.split()
        lines: list[str] = []
        current: list[str] = []
        for word in words:
            test = " ".join(current + [word])
            if self._font.getlength(test) < self.width - 20:
                current.append(word)
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))

        y = box_y + int(box_height * 0.1)
        for line in lines[:4]:
            bbox = draw.textbbox((0, 0), line, font=self._font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = max(0, (self.width - tw) // 2)
            draw.text((x, y), line, fill=WHITE, font=self._font)
            y += th + 4
