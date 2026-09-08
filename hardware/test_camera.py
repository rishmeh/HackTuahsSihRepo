#!/usr/bin/env python3
"""
Standalone camera + face test — captures frames from Pi camera and
sends them to the laptop for face detection + recognition.

Usage (on Pi):
    LAPTOP_URL=http://192.168.1.100:8000 python3 hardware/test_camera.py
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
        from hardware.camera import CameraCapture
    except ImportError:
        print("This test requires cv2 and httpx on the Pi.")
        sys.exit(1)

    print(f"Camera test → sending frames to {LAPTOP_URL}/hardware/process-frame")
    print("Press Ctrl+C to stop.\n")

    try:
        cap = CameraCapture(
            camera_type=os.getenv("CAMERA_TYPE", "auto"),
            index=int(os.getenv("CAMERA_INDEX", "0")),
        )
    except Exception as exc:
        print(f"ERROR: Could not open camera: {exc}")
        sys.exit(1)
    print(f"Camera mode: {cap.kind}")

    client = httpx.Client(timeout=5.0)
    frame_count = 0
    face_count_total = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Camera read failed, retrying...")
                time.sleep(0.5)
                continue

            # Encode as JPEG
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            files = {"image": ("frame.jpg", buffer.tobytes(), "image/jpeg")}

            try:
                resp = client.post(f"{LAPTOP_URL}/hardware/process-frame", files=files)
                if resp.status_code == 200:
                    result = resp.json()
                    face_count = result.get("face_count", 0)
                    student = result.get("student_id")
                    score = result.get("score", 0)
                    event = result.get("event")
                    command = result.get("command", {})

                    frame_count += 1
                    if face_count > 0:
                        face_count_total += 1
                        print(f"  Frame {frame_count}: {face_count} face(s) | "
                              f"student={student} | score={score:.3f} | "
                              f"event={event} | state={command.get('face_state')}")
                    else:
                        if frame_count % 10 == 0:
                            print(f"  Frame {frame_count}: no faces")
                else:
                    print(f"  ERROR: {resp.status_code} - {resp.text}")
            except Exception as exc:
                print(f"  Send failed: {exc}")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\nCamera test complete. {frame_count} frames sent, "
              f"{face_count_total} contained faces.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
