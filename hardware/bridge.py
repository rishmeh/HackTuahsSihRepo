"""Raspberry Pi camera, display and servo bridge for Table Tot.

The Pi performs no recognition, speech or application work. It captures JPEG
frames for the laptop and applies face-display and servo commands returned by
the laptop.

In display-only mode (no camera, no GPIO) the daemon just polls the laptop for
the current face_state and drives the pygame face animation.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)

LAPTOP_URL = os.getenv("LAPTOP_URL", "http://192.168.0.164:8000")
POLL_INTERVAL = 0.25
FRAME_INTERVAL = 0.5


# ---------------------------------------------------------------------------
# Optional heavy imports — fail gracefully on a headless / GPIO-less machine
# ---------------------------------------------------------------------------

def _try_import_servo():
    try:
        from hardware.gpio import ServoController  # noqa: F401
        return ServoController
    except Exception as exc:
        logger.info("ServoController unavailable (no GPIO?): %s", exc)
        return None


def _try_import_camera():
    try:
        from hardware.camera import CameraCapture  # noqa: F401
        return CameraCapture
    except Exception as exc:
        logger.info("CameraCapture unavailable: %s", exc)
        return None


_ServoController = _try_import_servo()
_CameraCapture = _try_import_camera()


class _NullServos:
    """Drop-in replacement when GPIO is not available."""

    def idle(self): pass
    def listen(self): pass
    def speak(self): pass
    def happy(self): pass
    def thinking(self): pass
    def focus(self): pass
    def cleanup(self): pass


class PeripheralDaemon:
    """Thin Pi driver: display, optional camera, optional servos."""

    def __init__(
        self,
        laptop_url: str = LAPTOP_URL,
        head_pin: int = 12,
        body_pin: int = 13,
        camera_index: int = 0,
        camera_type: str = "auto",
        display_driver: str = "hdmi",
        display_width: int = 800,
        display_height: int = 480,
        fullscreen: bool = True,
    ) -> None:
        self.laptop_url = laptop_url.rstrip("/")
        self.camera_index = camera_index
        self.camera_type = camera_type
        self._running = False
        self._current_servo_state = "idle"
        self._current_face_state = "idle"
        self._student_id: Optional[str] = None
        self._last_revision = -1
        self._poll_failures = 0

        self.http = httpx.Client(timeout=30.0, base_url=self.laptop_url)

        # ------------------------------------------------------------------
        # Servos — optional: log a warning and continue without them
        # ------------------------------------------------------------------
        if _ServoController is not None:
            try:
                self.servos = _ServoController(head_pin=head_pin, body_pin=body_pin)
                logger.info("ServoController initialised on pins %d/%d", head_pin, body_pin)
            except Exception as exc:
                logger.warning("Servos disabled: %s", exc)
                self.servos = _NullServos()
        else:
            logger.info("GPIO not available — running without servos")
            self.servos = _NullServos()

        # ------------------------------------------------------------------
        # Display
        # ------------------------------------------------------------------
        if display_driver == "st7789v":
            from hardware.st7789v_display import ST7789VDisplay
            self.display = ST7789VDisplay()
        elif display_driver == "hdmi":
            from hardware.display import Display
            self.display = Display(
                width=display_width,
                height=display_height,
                fullscreen=fullscreen,
            )
        else:
            raise ValueError("DISPLAY_DRIVER must be hdmi or st7789v")

        # ------------------------------------------------------------------
        # Camera — optional
        # ------------------------------------------------------------------
        self.camera = None
        self._poll_thread: Optional[threading.Thread] = None
        self._camera_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        logger.info(
            "Starting Pi bridge; laptop=%s camera=%s",
            self.laptop_url,
            self.camera_type,
        )
        self._running = True
        if not self._check_laptop():
            logger.warning("Laptop is offline at startup — will keep retrying")

        self.servos.idle()
        self.display.start()
        self.display.set_state("idle")

        # Camera is optional
        if self.camera_type != "off":
            self._start_camera()
        else:
            logger.info("Camera disabled (CAMERA_TYPE=off)")

        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="tabletot-poll"
        )
        self._poll_thread.start()

        if self.camera is not None:
            self._camera_thread = threading.Thread(
                target=self._camera_loop, daemon=True, name="tabletot-camera"
            )
            self._camera_thread.start()

    def stop(self) -> None:
        logger.info("Stopping Pi bridge")
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=3.0)
        if self._camera_thread:
            self._camera_thread.join(timeout=3.0)
        self.servos.cleanup()
        self.display.stop()
        if self.camera is not None:
            self.camera.release()
        self.http.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_laptop(self) -> bool:
        try:
            return self.http.get("/health", timeout=5.0).status_code == 200
        except Exception:
            return False

    def _start_camera(self) -> None:
        if _CameraCapture is None:
            logger.warning("CameraCapture module not importable — camera disabled")
            return
        try:
            self.camera = _CameraCapture(
                camera_type=self.camera_type,
                index=self.camera_index,
            )
            logger.info("Camera started (%s)", self.camera.kind)
        except Exception as exc:
            logger.warning("Camera disabled: %s", exc)
            self.camera = None

    # ------------------------------------------------------------------
    # Poll loop — laptop → Pi (face & servo commands)
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Poll the laptop for the current face/servo state every 250 ms."""
        while self._running:
            try:
                response = self.http.get("/hardware/state", timeout=2.0)
                if response.status_code == 200:
                    self._poll_failures = 0
                    self._apply_command(response.json())
                else:
                    logger.debug(
                        "Unexpected status from /hardware/state: %s",
                        response.status_code,
                    )
            except Exception as exc:
                self._poll_failures += 1
                if self._poll_failures == 12:  # ~3 seconds of silence
                    logger.warning("Laptop link lost; returning to idle")
                    self.servos.idle()
                    self.display.set_state("idle")
                    self._current_servo_state = "idle"
                    self._current_face_state = "idle"
                logger.debug("State poll failed: %s", exc)
            time.sleep(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Camera loop — Pi → laptop (JPEG frames for face recognition)
    # ------------------------------------------------------------------

    def _camera_loop(self) -> None:
        """Send one compressed JPEG approximately every 500 ms."""
        if self.camera is None:
            return
        while self._running:
            try:
                import cv2
                ok, frame = self.camera.read()
                if not ok or frame is None:
                    time.sleep(0.5)
                    continue
                encoded, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                )
                if encoded:
                    self._send_frame(buffer.tobytes())
            except Exception as exc:
                logger.warning("Camera stream error: %s", exc)
            time.sleep(FRAME_INTERVAL)

    def _send_frame(self, jpeg: bytes) -> None:
        try:
            response = self.http.post(
                "/hardware/process-frame",
                files={"image": ("frame.jpg", jpeg, "image/jpeg")},
                timeout=5.0,
            )
            if response.status_code != 200:
                logger.warning(
                    "Laptop rejected frame: HTTP %s", response.status_code
                )
                return
            result = response.json()
            self._student_id = result.get("student_id")
            self._apply_command(result.get("command") or {})
            if result.get("event") == "arrived":
                logger.info("Student recognised: %s", self._student_id)
            elif result.get("event") == "departed":
                logger.info("Student departed")
        except httpx.TimeoutException:
            logger.debug("Frame inference timed out; dropping frame")
        except Exception as exc:
            logger.debug("Frame upload failed: %s", exc)

    # ------------------------------------------------------------------
    # Apply a laptop command dict to the local peripherals
    # ------------------------------------------------------------------

    def _apply_command(self, command: dict) -> None:
        """Apply the display and servo portions of the laptop-owned state."""
        revision = int(command.get("revision", self._last_revision))
        servo_state = command.get("servo_state", "idle")
        face_state = command.get("face_state", "idle")

        # Skip if nothing changed
        if (
            revision == self._last_revision
            and servo_state == self._current_servo_state
            and face_state == self._current_face_state
        ):
            return

        self._last_revision = revision

        # -- Face display --
        if face_state != self._current_face_state:
            logger.info("Face: %s → %s", self._current_face_state, face_state)
            self.display.set_state(face_state)
            self._current_face_state = face_state

        overlay_text = command.get("overlay_text")
        if overlay_text:
            self.display.show_text(
                overlay_text,
                duration=command.get("overlay_duration"),
            )

        # -- Servos --
        if servo_state == self._current_servo_state:
            return

        actions = {
            "idle":      self.servos.idle,
            "listening": self.servos.listen,
            "speaking":  self.servos.speak,
            "happy":     self.servos.happy,
            "thinking":  self.servos.thinking,
            "focus":     self.servos.focus,
            "sleeping":  self.servos.idle,
        }
        action = actions.get(servo_state)
        if action is None:
            logger.warning("Unknown servo state %r — ignoring", servo_state)
            return
        action()
        self._current_servo_state = servo_state

    # ------------------------------------------------------------------
    # Telemetry (best-effort — failures are silent)
    # ------------------------------------------------------------------

    def _report_telemetry(self) -> None:
        try:
            self.http.post(
                "/hardware/state/set",
                json={
                    "servo_state": self._current_servo_state,
                    "face_state": self._current_face_state,
                    "student_id": self._student_id,
                    "camera_active": self.camera is not None,
                    "camera_type": self.camera.kind if self.camera else "off",
                    "display_active": True,
                },
                timeout=2.0,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.start()

        def signal_handler(signum, frame) -> None:
            del frame
            logger.info("Signal %s received — stopping", signum)
            self.stop()
            raise SystemExit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        try:
            while self._running:
                self._report_telemetry()
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    PeripheralDaemon(
        laptop_url=LAPTOP_URL,
        camera_index=int(os.getenv("CAMERA_INDEX", "0")),
        camera_type=os.getenv("CAMERA_TYPE", "off"),
        display_driver=os.getenv("DISPLAY_DRIVER", "hdmi").lower(),
        display_width=int(os.getenv("DISPLAY_WIDTH", "800")),
        display_height=int(os.getenv("DISPLAY_HEIGHT", "480")),
        fullscreen=os.getenv("DISPLAY_FULLSCREEN", "true").lower() == "true",
    ).run()


if __name__ == "__main__":
    main()

