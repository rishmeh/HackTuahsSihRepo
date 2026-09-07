#!/usr/bin/env python3
"""
Standalone vision test — sends a single frame to the laptop for face detection
and prints the result.

Usage (on Pi):
    LAPTOP_URL=http://192.168.1.100:8000 python3 hardware/test_vision.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LAPTOP_URL = os.getenv("LAPTOP_URL", "http://localhost:8000")


def main():
    try:
        import cv2
        import httpx
    except ImportError:
        print("This test requires cv2 and httpx on the Pi.")
        sys.exit(1)

    print(f"Vision test → sending frame to {LAPTOP_URL}/hardware/process-frame\n")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera.")
        sys.exit(1)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("ERROR: Could not capture frame.")
        sys.exit(1)

    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    files = {"image": ("frame.jpg", buffer.tobytes(), "image/jpeg")}

    try:
        resp = httpx.post(f"{LAPTOP_URL}/hardware/process-frame", files=files, timeout=10.0)
        if resp.status_code == 200:
            result = resp.json()
            print("Vision result:")
            print(f"  face_count: {result.get('face_count')}")
            print(f"  student_id: {result.get('student_id')}")
            print(f"  score:      {result.get('score')}")
            print(f"  faces:      {result.get('faces')}")
        else:
            print(f"ERROR: {resp.status_code} - {resp.text}")
    except Exception as exc:
        print(f"Request failed: {exc}")


if __name__ == "__main__":
    main()
