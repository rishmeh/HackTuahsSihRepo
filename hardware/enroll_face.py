#!/usr/bin/env python3
"""Capture face samples on the Pi and enroll them in the laptop brain."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.camera import CameraCapture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("student_id", help="ID already used by the learner profile")
    parser.add_argument("--frames", type=int, default=8, choices=range(3, 21))
    parser.add_argument("--interval", type=float, default=0.7)
    args = parser.parse_args()

    laptop_url = os.getenv("LAPTOP_URL", "http://127.0.0.1:8000").rstrip("/")
    camera = CameraCapture(
        camera_type=os.getenv("CAMERA_TYPE", "auto"),
        index=int(os.getenv("CAMERA_INDEX", "0")),
    )
    samples: list[tuple[str, tuple[str, bytes, str]]] = []

    print(f"Using {camera.kind} camera. Look at the camera and vary your angle slightly.")
    try:
        for index in range(args.frames):
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("camera returned no frame")
            encoded, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not encoded:
                raise RuntimeError("could not encode camera frame")
            samples.append(
                ("images", (f"face-{index + 1}.jpg", buffer.tobytes(), "image/jpeg"))
            )
            print(f"Captured {index + 1}/{args.frames}")
            if index + 1 < args.frames:
                time.sleep(args.interval)
    finally:
        camera.release()

    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{laptop_url}/vision/face/enroll",
            data={"student_id": args.student_id},
            files=samples,
        )
    if response.status_code != 200:
        print(f"Enrollment failed ({response.status_code}): {response.text}")
        return 1
    result = response.json()
    print(
        f"Enrolled {result['student_id']}: {result['embeddings_added']} new samples, "
        f"{result['frames_rejected']} rejected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
