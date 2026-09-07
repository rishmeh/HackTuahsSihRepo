"""Camera capture adapters for the Pi peripheral daemon.

``auto`` prefers a Pi CSI camera through Picamera2 and falls back to a USB
UVC camera through OpenCV.  Frames leave the Pi as JPEG; no vision model runs
here.
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraCapture:
    def __init__(
        self,
        camera_type: str = "auto",
        index: int = 0,
        width: int = 640,
        height: int = 480,
    ) -> None:
        if camera_type not in {"auto", "csi", "usb", "off"}:
            raise ValueError("CAMERA_TYPE must be auto, csi, usb, or off")
        self.kind = "off"
        self._picamera = None
        self._capture: Optional[cv2.VideoCapture] = None

        if camera_type == "off":
            return
        if camera_type in {"auto", "csi"}:
            try:
                from picamera2 import Picamera2

                camera = Picamera2()
                configuration = camera.create_video_configuration(
                    main={"size": (width, height), "format": "RGB888"},
                    buffer_count=2,
                )
                camera.configure(configuration)
                camera.start()
                self._picamera = camera
                self.kind = "csi"
                logger.info("CSI camera started at %dx%d", width, height)
                return
            except Exception as exc:
                if camera_type == "csi":
                    raise RuntimeError(f"could not start CSI camera: {exc}") from exc
                logger.info("CSI camera unavailable, trying USB camera: %s", exc)

        capture = cv2.VideoCapture(index)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"could not open USB camera index {index}")
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture = capture
        self.kind = "usb"
        logger.info("USB camera %d started at %dx%d", index, width, height)

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        if self._picamera is not None:
            rgb = self._picamera.capture_array()
            return True, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if self._capture is not None:
            ok, frame = self._capture.read()
            return ok, frame if ok else None
        return False, None

    def release(self) -> None:
        if self._picamera is not None:
            self._picamera.stop()
            self._picamera.close()
            self._picamera = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
