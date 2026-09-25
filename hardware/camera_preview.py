#!/usr/bin/env python3
"""
camera_preview.py — View live feed or snap a photo from the Pi USB camera.

Features:
  1. Saves a snapshot 'snapshot.jpg' immediately on startup.
  2. Serves a live MJPEG video stream over HTTP on port 8080.
     You can open http://<PI_IP>:8080 on your laptop browser to see the live camera feed!

Usage:
    python3 hardware/camera_preview.py
    python3 hardware/camera_preview.py --snapshot-only
    python3 hardware/camera_preview.py --index 0 --port 8080
"""

import argparse
import io
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

try:
    import cv2
except ImportError:
    print("[ERROR] OpenCV (cv2) is required. Run: pip install opencv-python-headless")
    sys.exit(1)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class CameraStreamHandler(BaseHTTPRequestHandler):
    camera = None

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Table Tot — Pi USB Camera Live Stream</title>
    <style>
        body {{
            background: #111;
            color: #eee;
            font-family: system-ui, -apple-system, sans-serif;
            text-align: center;
            padding: 20px;
        }}
        h1 {{ margin-bottom: 5px; }}
        p {{ color: #888; margin-top: 0; }}
        .stream-box {{
            display: inline-block;
            border: 3px solid #00c864;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,200,100,0.3);
            background: #000;
        }}
        img {{ display: block; max-width: 100%; height: auto; }}
        .badge {{
            background: #00c864;
            color: #000;
            padding: 4px 10px;
            border-radius: 4px;
            font-weight: bold;
            display: inline-block;
            margin-bottom: 15px;
        }}
    </style>
</head>
<body>
    <div class="badge">● LIVE FEED</div>
    <h1>Table Tot Camera Preview</h1>
    <p>Live stream directly from Raspberry Pi USB camera</p>
    <div class="stream-box">
        <img src="/stream.mjpg" width="640" height="480" alt="Camera Stream" />
    </div>
    <p style="margin-top: 20px;">Snapshot saved locally as <code>snapshot.jpg</code></p>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    ok, frame = self.camera.read()
                    if not ok or frame is None:
                        time.sleep(0.05)
                        continue
                    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpeg)))
                    self.end_headers()
                    self.wfile.write(jpeg.tobytes())
                    self.wfile.write(b"\r\n")
                    time.sleep(0.033)  # ~30 fps
            except (ConnectionResetError, BrokenPipeError):
                pass
        else:
            self.send_error(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress noisy HTTP GET logging in console
        pass


def main():
    parser = argparse.ArgumentParser(description="Pi USB Camera Preview and Stream")
    parser.add_argument("--index", type=int, default=0, help="V4L2 camera index (default: 0)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP streaming port (default: 8080)")
    parser.add_argument("--snapshot-only", action="store_true", help="Snap one photo and exit")
    args = parser.parse_args()

    print("\n" + "=" * 55)
    print(f"  Table Tot — USB Camera Preview (Index {args.index})")
    print("=" * 55)

    print(f"[1/3] Opening camera index {args.index} via V4L2...")
    cap = cv2.VideoCapture(args.index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(args.index)

    if not cap.isOpened():
        print(f"\n[ERROR] Failed to open camera index {args.index}!")
        print("Check if the camera is detected:")
        print("  ls -l /dev/video*")
        print("  v4l2-ctl --list-devices")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print("[2/3] Capturing test snapshot...")
    # Read a couple frames to let auto-exposure adjust
    for _ in range(5):
        cap.read()
        time.sleep(0.05)

    ret, frame = cap.read()
    if not ret or frame is None:
        print("[ERROR] Camera opened but failed to read frames.")
        cap.release()
        sys.exit(1)

    filename = "snapshot.jpg"
    cv2.imwrite(filename, frame)
    h, w = frame.shape[:2]
    print(f"      ✓ Snapshot saved successfully: '{filename}' ({w}x{h})")

    if args.snapshot_only:
        cap.release()
        print("\nDone! Exiting (--snapshot-only requested).")
        return

    # Serve live stream
    local_ip = get_local_ip()
    stream_url = f"http://{local_ip}:{args.port}"
    print("\n[3/3] Starting live video stream...")
    print("=" * 55)
    print(f"  👉 LIVE STREAM URL: {stream_url}")
    print("=" * 55)
    print("\nOpen that URL in Chrome/Edge on your laptop to watch the live feed!")
    print("Press Ctrl+C to stop.\n")

    CameraStreamHandler.camera = cap
    server = HTTPServer(("0.0.0.0", args.port), CameraStreamHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping camera stream...")
    finally:
        server.server_close()
        cap.release()
        print("Camera released cleanly.")


if __name__ == "__main__":
    main()
