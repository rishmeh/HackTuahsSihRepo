"""BeagleBone Black USB camera / ST7789 SPI display / PRU-servo bridge for Table Tot."""

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

from beaglebone_experiment.pru_servo import PruServoController
from beaglebone_experiment.spi_display import SpiDisplay

logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.25
FRAME_INTERVAL = 0.5


class BeagleBoneBridge:
    def __init__(self) -> None:
        self.laptop_url = os.environ["LAPTOP_URL"].rstrip("/")
        self.http = httpx.Client(base_url=self.laptop_url, timeout=10.0)
        self.servos = PruServoController(
            head_min_us=int(os.getenv("HEAD_MIN_US", "1000")),
            head_max_us=int(os.getenv("HEAD_MAX_US", "2000")),
            body_min_us=int(os.getenv("BODY_MIN_US", "1000")),
            body_max_us=int(os.getenv("BODY_MAX_US", "2000")),
        )
        self.display = SpiDisplay(
            width=int(os.getenv("DISPLAY_WIDTH", "240")),
            height=int(os.getenv("DISPLAY_HEIGHT", "240")),
            fullscreen=True,
            rotation=int(os.getenv("DISPLAY_ROTATION", "0")),
            bgr=os.getenv("DISPLAY_BGR", "false").lower() == "true",
            col_offset=int(os.getenv("DISPLAY_COL_OFFSET", "0")),
            row_offset=int(os.getenv("DISPLAY_ROW_OFFSET", "0")),
        )
        self.camera = cv2.VideoCapture(int(os.getenv("CAMERA_INDEX", "0")))
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(os.getenv("CAMERA_WIDTH", "640")))
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(os.getenv("CAMERA_HEIGHT", "480")))
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.camera.isOpened():
            raise RuntimeError("USB camera cannot be opened; verify CAMERA_INDEX and /dev/video*")
        self._running = False
        self._servo_state = "idle"
        self._face_state = "idle"
        self._revision = -1
        self._student_id: Optional[str] = None
        self._failures = 0

    def start(self) -> None:
        self._running = True
        self.servos.set_angles(0, 0)
        self.display.start()
        self.display.set_state("idle")
        threading.Thread(target=self._poll_loop, name="bb-state-poll", daemon=True).start()
        threading.Thread(target=self._camera_loop, name="bb-camera", daemon=True).start()
        logger.info("BBB bridge started; laptop=%s", self.laptop_url)

    def stop(self) -> None:
        self._running = False
        self.servos.cleanup()
        self.display.stop()
        self.camera.release()
        self.http.close()

    def _poll_loop(self) -> None:
        while self._running:
            try:
                response = self.http.get("/hardware/state", timeout=2.0)
                response.raise_for_status()
                self._failures = 0
                self._apply_command(response.json())
            except Exception as exc:
                self._failures += 1
                if self._failures == 12:
                    logger.warning("Laptop link lost; returning face and servos to neutral")
                    self.display.set_state("idle")
                    self.servos.set_angles(0, 0)
                logger.debug("state poll failed: %s", exc)
            time.sleep(POLL_INTERVAL)

    def _camera_loop(self) -> None:
        while self._running:
            ok, frame = self.camera.read()
            if not ok:
                logger.warning("USB camera frame read failed")
                time.sleep(FRAME_INTERVAL)
                continue
            encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if encoded:
                try:
                    response = self.http.post(
                        "/hardware/process-frame",
                        files={"image": ("frame.jpg", jpeg.tobytes(), "image/jpeg")},
                        timeout=5.0,
                    )
                    response.raise_for_status()
                    result = response.json()
                    self._student_id = result.get("student_id")
                    self._apply_command(result.get("command") or {})
                except Exception as exc:
                    logger.debug("frame upload failed: %s", exc)
            time.sleep(FRAME_INTERVAL)

    def _apply_command(self, command: dict) -> None:
        revision = int(command.get("revision", self._revision))
        servo_state = command.get("servo_state", "idle")
        face_state = command.get("face_state", "idle")
        if revision == self._revision and servo_state == self._servo_state and face_state == self._face_state:
            return
        self._revision = revision
        if face_state != self._face_state:
            self.display.set_state(face_state)
            self._face_state = face_state
        if command.get("overlay_text"):
            self.display.show_text(command["overlay_text"], command.get("overlay_duration"))
        if servo_state != self._servo_state:
            self._gesture(servo_state)
            self._servo_state = servo_state

    def _gesture(self, state: str) -> None:
        poses = {
            "idle": [(0, 0, 0.1)],
            "listening": [(15, 0, 0.1)],
            "speaking": [(8, -4, 0.18), (-2, 4, 0.18), (8, -4, 0.18)],
            "happy": [(18, -15, 0.20), (-5, 15, 0.20), (18, -12, 0.20), (0, 0, 0.1)],
            "thinking": [(-15, 7, 0.1)],
            "focus": [(0, -5, 0.1)],
            "sleeping": [(0, 0, 0.1)],
        }.get(state)
        if poses is None:
            logger.warning("Ignoring unknown servo state %r", state)
            return

        def run() -> None:
            for head, body, hold in poses:
                if not self._running:
                    return
                self.servos.set_angles(head, body)
                time.sleep(hold)

        threading.Thread(target=run, name="bb-servo-gesture", daemon=True).start()

    def run(self) -> None:
        self.start()
        try:
            while self._running:
                time.sleep(1.0)
        finally:
            self.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    bridge = BeagleBoneBridge()
    signal.signal(signal.SIGINT, lambda *_: setattr(bridge, "_running", False))
    signal.signal(signal.SIGTERM, lambda *_: setattr(bridge, "_running", False))
    bridge.run()


if __name__ == "__main__":
    main()
