"""Face renderer for the 240x320 SPI ST7789V GMT020-02-8P display.

Wiring uses SPI0 CE0 plus BCM GPIO 25 (DC), 24 (reset), and 9 (backlight).
It targets Raspberry Pi 5's RP1 GPIO controller via ``lgpio``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import lgpio
import spidev
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

WIDTH = 240
HEIGHT = 320
SPI_SPEED_HZ = 20_000_000
DC_PIN = 25
RESET_PIN = 24
BACKLIGHT_PIN = 9
VALID_STATES = {"idle", "listening", "speaking", "thinking", "happy", "sleeping", "focus"}
BLACK, CYAN = (0, 0, 0), (0, 255, 255)
PIXEL_SCALE = 8
LANDSCAPE_WIDTH, LANDSCAPE_HEIGHT = HEIGHT // PIXEL_SCALE, WIDTH // PIXEL_SCALE
EYES = {
    "idle": ["##  ##", "##  ##", "##  ##"], "listening": ["##  ##", "### ###", "##  ##"],
    "thinking": ["##    ", "##  ##", "    ##"], "happy": [" ##  ## ", "##    ##", "        "],
    "focus": ["###  ###", "###  ###", "###  ###"], "sleeping": ["        ", "##    ##", "        "],
}
MOUTHS = {
    "idle": [" ## "], "listening": ["####"], "thinking": ["##  ", "  ##"],
    "happy": ["##  ##", " #### ", "  ##  "], "focus": ["####"], "sleeping": ["    ", " ## "],
    "speaking_a": [" #### "], "speaking_b": ["  ##  ", " #### ", "  ##  "],
}


def _open_gpio_chip() -> tuple[int, int]:
    """Find RP1 on a Pi 5, with a safe fallback for other Pi OS layouts."""
    tried: list[int] = []
    for name in os.listdir("/sys/class/gpio"):
        # The supplied working driver finds Pi 5's RP1 entries as ``chipN``;
        # other Pi OS images expose ``gpiochipN``. Support both spellings.
        if name.startswith("chip"):
            index = int(name.removeprefix("chip"))
        elif name.startswith("gpiochip"):
            index = int(name.removeprefix("gpiochip"))
        else:
            continue
        label_path = f"/sys/class/gpio/{name}/label"
        try:
            with open(label_path, encoding="utf-8") as label_file:
                label = label_file.read().lower()
            if "rp1" in label:
                tried.append(index)
                try:
                    return lgpio.gpiochip_open(index), index
                except Exception:
                    # Some Pi OS releases expose an RP1 label on a chip that
                    # lgpio cannot open; continue to the device-node scan.
                    continue
        except OSError:
            continue
    for index in reversed(list(range(16)) + [569]):
        if os.path.exists(f"/dev/gpiochip{index}"):
            if index in tried:
                continue
            tried.append(index)
            try:
                return lgpio.gpiochip_open(index), index
            except Exception:
                continue
    checked = ", ".join(f"gpiochip{index}" for index in tried) or "none"
    raise RuntimeError(
        "lgpio could not open a GPIO chip (checked: " + checked + "). "
        "Verify python3-lgpio is installed and that the current user may access /dev/gpiochip*."
    )


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
        # Face-only panel: laptop greetings must not alter the black background.
        del text, duration

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

    def _draw_face(self, state: str, overlay: Optional[str], elapsed: float) -> Image.Image:
        del overlay
        canvas = Image.new("RGB", (LANDSCAPE_WIDTH, LANDSCAPE_HEIGHT), BLACK)
        draw = ImageDraw.Draw(canvas)
        frame = int(elapsed * 4)
        eyes = EYES["idle" if state == "speaking" else state]
        if state != "sleeping" and frame % 16 == 0:
            eyes = ["##  ##"]  # one short, subtle blink
        self._draw_sprite(draw, eyes, (LANDSCAPE_WIDTH - max(map(len, eyes))) // 2, 8)
        mouth = MOUTHS["speaking_a" if frame % 2 == 0 else "speaking_b"] if state == "speaking" else MOUTHS[state]
        self._draw_sprite(draw, mouth, (LANDSCAPE_WIDTH - max(map(len, mouth))) // 2, 18)
        if state == "thinking":
            self._draw_sprite(draw, ["#" * ((frame % 3) + 1)], 32, 6)
        # Preserve the proven portrait controller/window setup and rotate only
        # the composition, producing a horizontal face layout on the mounted TFT.
        return canvas.resize((HEIGHT, WIDTH), Image.Resampling.NEAREST).transpose(Image.Transpose.ROTATE_90)

    @staticmethod
    def _draw_sprite(draw: ImageDraw.ImageDraw, sprite: list[str], x: int, y: int) -> None:
        for row, line in enumerate(sprite):
            for column, pixel in enumerate(line):
                if pixel == "#":
                    draw.point((x + column, y + row), fill=CYAN)
