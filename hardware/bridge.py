"""Raspberry Pi camera, display and servo bridge for Table Tot.

The Pi performs no recognition, speech or application work. It captures JPEG
frames for the laptop and applies face-display and servo commands returned by
the laptop.
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

import cv2
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.camera import CameraCapture  # noqa: E402
from hardware.display import Display  # noqa: E402
from hardware.gpio import ServoController  # noqa: E402

logger = logging.getLogger(__name__)

LAPTOP_URL = os.getenv("LAPTOP_URL", "http://192.168.1.100:8000")
POLL_INTERVAL = 0.25
FRAME_INTERVAL = 0.5


class PeripheralDaemon:
    """Thin Pi driver for one camera and two servos."""

    def __init__(
        self,
        laptop_url: str = LAPTOP_URL,
        head_pin: int = 12,
        body_pin: int = 13,
        camera_index: int = 0,
        camera_type: str = "auto",
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
        self.servos = ServoController(head_pin=head_pin, body_pin=body_pin)
        self.display = Display(
            width=display_width,
            height=display_height,
            fullscreen=fullscreen,
        )
        self.camera: Optional[CameraCapture] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._camera_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        logger.info("Starting Pi camera/display/servo bridge; laptop=%s", self.laptop_url)
        self._running = True
        if not self._check_laptop():
            logger.warning("Laptop is offline; the bridge will keep retrying")

        self.servos.idle()
        self.display.start()
        self.display.set_state("idle")
        self._start_camera()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._poll_thread.start()
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
        if self.camera:
            self.camera.release()
        self.http.close()

    def _check_laptop(self) -> bool:
        try:
            return self.http.get("/health", timeout=5.0).status_code == 200
        except Exception:
            return False

    def _start_camera(self) -> None:
        try:
            self.camera = CameraCapture(
                camera_type=self.camera_type,
                index=self.camera_index,
            )
        except Exception as exc:
            logger.error("Camera disabled: %s", exc)

    def _poll_loop(self) -> None:
        """Laptop to Pi: poll the latest face and servo command as small JSON."""
        while self._running:
            try:
                response = self.http.get("/hardware/state", timeout=2.0)
                if response.status_code == 200:
                    self._poll_failures = 0
                    self._apply_command(response.json())
            except Exception as exc:
                self._poll_failures += 1
                if self._poll_failures == 12:
                    logger.warning("Laptop link lost; returning servos to neutral")
                    self.servos.idle()
                    self.display.set_state("idle")
                    self._current_servo_state = "idle"
                    self._current_face_state = "idle"
                logger.debug("Servo command poll failed: %s", exc)
            time.sleep(POLL_INTERVAL)

    def _camera_loop(self) -> None:
        """Pi to laptop: send one compressed JPEG approximately every 500 ms."""
        if self.camera is None:
            return
        while self._running:
            try:
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
                logger.warning("Laptop rejected frame: HTTP %s", response.status_code)
                return
            result = response.json()
            self._student_id = result.get("student_id")
            self._apply_command(result.get("command") or {})
            if result.get("event") == "arrived":
                logger.info("Laptop recognized student %s", self._student_id)
            elif result.get("event") == "departed":
                logger.info("Laptop reports that the student left")
        except httpx.TimeoutException:
            logger.debug("Frame inference timed out; dropping this frame")
        except Exception as exc:
            logger.debug("Frame upload failed: %s", exc)

    def _apply_command(self, command: dict) -> None:
        """Apply the display and servo portions of the laptop-owned state."""
        revision = int(command.get("revision", self._last_revision))
        servo_state = command.get("servo_state", "idle")
        face_state = command.get("face_state", "idle")
        if (
            revision == self._last_revision
            and servo_state == self._current_servo_state
            and face_state == self._current_face_state
        ):
            return
        self._last_revision = revision
        if face_state != self._current_face_state:
            self.display.set_state(face_state)
            self._current_face_state = face_state
        overlay_text = command.get("overlay_text")
        if overlay_text:
            self.display.show_text(
                overlay_text,
                duration=command.get("overlay_duration"),
            )
        if servo_state == self._current_servo_state:
            return
        actions = {
            "idle": self.servos.idle,
            "listening": self.servos.listen,
            "speaking": self.servos.speak,
            "happy": self.servos.happy,
            "thinking": self.servos.thinking,
            "focus": self.servos.focus,
            "sleeping": self.servos.idle,
        }
        action = actions.get(servo_state)
        if action is None:
            logger.warning("Ignoring unknown servo state %r", servo_state)
            return
        action()
        self._current_servo_state = servo_state

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

    def run(self) -> None:
        self.start()

        def signal_handler(signum, frame) -> None:
            del frame
            logger.info("Received signal %s", signum)
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
        camera_index=int(os.getenv("CAMERA_INDEX", "0")),
        camera_type=os.getenv("CAMERA_TYPE", "auto"),
        display_width=int(os.getenv("DISPLAY_WIDTH", "800")),
        display_height=int(os.getenv("DISPLAY_HEIGHT", "480")),
        fullscreen=os.getenv("DISPLAY_FULLSCREEN", "true").lower() == "true",
    ).run()


if __name__ == "__main__":
    main()
