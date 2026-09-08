"""Face renderer for the 240x320 SPI ST7789V GMT020-02-8P display.

Wiring uses SPI0 CE0 plus BCM GPIO 25 (DC), 24 (reset), and 9 (backlight).
It targets Raspberry Pi 5's RP1 GPIO controller via ``lgpio``.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import Optional

import lgpio
import spidev
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WIDTH = 240
HEIGHT = 320
SPI_SPEED_HZ = 20_000_000
DC_PIN = 25
RESET_PIN = 24
BACKLIGHT_PIN = 9
VALID_STATES = {"idle", "listening", "speaking", "thinking", "happy", "sleeping", "focus"}


def _open_gpio_chip() -> tuple[int, int]:
    """Find RP1 on a Pi 5, with a safe fallback for other Pi OS layouts."""
    for name in os.listdir("/sys/class/gpio"):
        if not name.startswith("gpiochip"):
            continue
        label_path = f"/sys/class/gpio/{name}/label"
        try:
            with open(label_path, encoding="utf-8") as label_file:
                label = label_file.read().lower()
            if "rp1" in label:
                index = int(name.removeprefix("gpiochip"))
                return lgpio.gpiochip_open(index), index
        except OSError:
            continue
    for index in range(32):
        if os.path.exists(f"/dev/gpiochip{index}"):
            try:
                return lgpio.gpiochip_open(index), index
            except Exception:
                continue
    raise RuntimeError("No usable GPIO chip found for the ST7789V display")


class ST7789VDisplay:
    """Thread-safe animated face display over SPI; same public API as Display."""

    def __init__(self, fps: int = 10, spi_speed_hz: int = SPI_SPEED_HZ) -> None:
        self.width, self.height = WIDTH, HEIGHT
        self._fps = max(1, min(int(fps), 16))
        self._state = "idle"
        self._overlay: Optional[str] = None
        self._overlay_deadline = 0.0
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._started_at = 0.0
        self._chip, self._chip_number = _open_gpio_chip()
        try:
            for pin in (DC_PIN, RESET_PIN, BACKLIGHT_PIN):
                lgpio.gpio_claim_output(self._chip, pin, 0)
            self._spi = spidev.SpiDev()
            self._spi.open(0, 0)  # SPI0 CE0 = physical pin 24
            self._spi.mode = 0
            self._spi.max_speed_hz = spi_speed_hz
            self._reset_and_initialise()
            lgpio.gpio_write(self._chip, BACKLIGHT_PIN, 1)
        except Exception:
            lgpio.gpiochip_close(self._chip)
            raise

    def start(self) -> None:
        self._running = True
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="tabletot-st7789v", daemon=True)
        self._thread.start()
        logger.info("ST7789V face display started on gpiochip%s", self._chip_number)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        try:
            lgpio.gpio_write(self._chip, BACKLIGHT_PIN, 0)
            self._spi.close()
        finally:
            lgpio.gpiochip_close(self._chip)

    @property
    def current_state(self) -> str:
        with self._lock:
            return self._state

    def set_state(self, state: str) -> None:
        if state not in VALID_STATES:
            logger.warning("Invalid ST7789V face state %r; using idle", state)
            state = "idle"
        with self._lock:
            self._state = state

    def show_text(self, text: str, duration: Optional[float] = None) -> None:
        with self._lock:
            self._overlay = text
            self._overlay_deadline = time.monotonic() + duration if duration else 0.0

    def clear_text(self) -> None:
        with self._lock:
            self._overlay = None
            self._overlay_deadline = 0.0

    def _command(self, value: int) -> None:
        lgpio.gpio_write(self._chip, DC_PIN, 0)
        self._spi.writebytes([value & 0xFF])

    def _data(self, values: bytes | bytearray | list[int] | int) -> None:
        lgpio.gpio_write(self._chip, DC_PIN, 1)
        if isinstance(values, int):
            self._spi.writebytes([values & 0xFF])
            return
        for offset in range(0, len(values), 4096):
            self._spi.writebytes(values[offset : offset + 4096])

    def _reset_and_initialise(self) -> None:
        lgpio.gpio_write(self._chip, RESET_PIN, 1)
        time.sleep(0.05)
        lgpio.gpio_write(self._chip, RESET_PIN, 0)
        time.sleep(0.05)
        lgpio.gpio_write(self._chip, RESET_PIN, 1)
        time.sleep(0.15)
        # These settings and the 240x320 address window match GMT020-02-8P.
        self._command(0x36); self._data(0x00)  # portrait, RGB order
        self._command(0x3A); self._data(0x05)  # RGB565
        self._command(0x21)                    # display inversion on
        self._command(0x11); time.sleep(0.12)  # sleep out
        self._command(0x29); time.sleep(0.05)  # display on

    def _present(self, image: Image.Image) -> None:
        rgb = image.convert("RGB")
        pixels = rgb.tobytes()
        frame = bytearray(len(pixels) // 3 * 2)
        write = 0
        for index in range(0, len(pixels), 3):
            red, green, blue = pixels[index : index + 3]
            value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
            frame[write] = value >> 8
            frame[write + 1] = value & 0xFF
            write += 2
        self._command(0x2A); self._data([0, 0, 0, WIDTH - 1])
        self._command(0x2B); self._data([0, 0, 1, HEIGHT - 1])
        self._command(0x2C); self._data(frame)

    def _loop(self) -> None:
        interval = 1.0 / self._fps
        while self._running:
            started = time.monotonic()
            with self._lock:
                if self._overlay_deadline and started >= self._overlay_deadline:
                    self._overlay, self._overlay_deadline = None, 0.0
                state, overlay = self._state, self._overlay
            self._present(self._draw_face(state, overlay, started - self._started_at))
            time.sleep(max(0.0, interval - (time.monotonic() - started)))

    @staticmethod
    def _font(size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()

    def _draw_face(self, state: str, overlay: Optional[str], elapsed: float) -> Image.Image:
        image = Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 20))
        draw = ImageDraw.Draw(image)
        color = {"listening": (0, 150, 255), "happy": (0, 200, 100), "thinking": (255, 180, 0)}.get(state, (240, 240, 240))
        blink = state == "sleeping" or elapsed % 4.0 < 0.16
        centers = (75, 165)
        if blink:
            for x in centers:
                draw.line((x - 25, 125, x + 25, 125), fill=(240, 240, 240), width=4)
        else:
            for x in centers:
                draw.ellipse((x - 27, 92, x + 27, 158), fill=color)
                draw.ellipse((x - 11, 111, x + 11, 139), fill=(20, 20, 20))
                draw.ellipse((x - 6, 114, x, 120), fill=(240, 240, 240))
        if state in {"thinking", "happy", "listening"}:
            brow = color
            if state == "thinking":
                draw.line((48, 77, 100, 90), fill=brow, width=4); draw.line((140, 90, 192, 77), fill=brow, width=4)
            else:
                draw.line((48, 83, 100, 83), fill=brow, width=4); draw.line((140, 83, 192, 83), fill=brow, width=4)
        white = (240, 240, 240)
        if state == "happy":
            draw.arc((78, 177, 162, 225), start=10, end=170, fill=white, width=5)
        elif state == "speaking":
            open_height = 13 + int(16 * abs(math.sin(elapsed * 8)))
            draw.ellipse((78, 191 - open_height // 2, 162, 191 + open_height // 2), fill=white)
        elif state == "thinking":
            draw.arc((96, 185, 145, 210), start=210, end=340, fill=white, width=4)
        elif state == "listening":
            draw.arc((78, 178, 162, 222), start=15, end=165, fill=white, width=4)
        else:
            draw.arc((96, 185, 145, 210), start=210, end=340, fill=white, width=4)
        if overlay:
            draw.rectangle((0, 258, WIDTH, HEIGHT), fill=(0, 0, 0))
            text = overlay[:34]
            font = self._font(16)
            bounds = draw.textbbox((0, 0), text, font=font)
            draw.text(((WIDTH - (bounds[2] - bounds[0])) // 2, 282), text, fill=white, font=font)
        return image
