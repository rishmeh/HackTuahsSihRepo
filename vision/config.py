"""
vision/config.py — Configuration for the face detection and recognition package.

Deliberately self-contained: this package sits outside ml/ and must not import
ml/config.py, so it can be used on its own (by the robot's camera loop, or a
future standalone vision service) as well as mounted into the ml API.

Every value can be overridden with an environment variable, and every default
below is calibrated against measurement rather than taste — see the comments.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional for library-only use
    pass

# Package directory, so paths work regardless of the current working directory.
PACKAGE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Pretrained model weights
# ---------------------------------------------------------------------------
# Fetch both once with: python -m vision.download_models
#
# These live in weights/ rather than models/ because vision/models.py already
# exists and holds the dataclasses — two different meanings of "model".
WEIGHTS_DIR: Path = Path(os.getenv("VISION_WEIGHTS_DIR", PACKAGE_DIR / "weights"))

YUNET_MODEL_PATH: Path = Path(
    os.getenv("YUNET_MODEL_PATH", WEIGHTS_DIR / "face_detection_yunet_2023mar.onnx")
)
SFACE_MODEL_PATH: Path = Path(
    os.getenv("SFACE_MODEL_PATH", WEIGHTS_DIR / "face_recognition_sface_2021dec.onnx")
)

# ---------------------------------------------------------------------------
# Enrolled faces
# ---------------------------------------------------------------------------
# Embeddings only — never images. See face_store.py.
FACE_DB_PATH: Path = Path(os.getenv("FACE_DB_PATH", PACKAGE_DIR / "data" / "faces.db"))

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
# Detector confidence required to call something a face.
#
# Calibrated against measurement: a moving face is reported at a median of 0.833
# and dips well below, while the worst false positive on a faceless image scored
# 0.585. 0.70 sits between them. Raising this towards 0.9 makes the robot lose
# the student whenever they move; lowering it past ~0.59 invents faces.
FACE_DETECT_THRESHOLD: float = float(os.getenv("FACE_DETECT_THRESHOLD", "0.70"))

# Cosine similarity required to accept an identity.
#
# Measured: the same person scores ~0.94, two different people ~0.20. OpenCV's
# published figure is 0.363; ours is stricter because a false reject costs one
# spoken "who are you?", while a false accept silently loads another student's
# persona, progress and revision queue.
FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.45"))

# ---------------------------------------------------------------------------
# Presence smoothing
# ---------------------------------------------------------------------------
# Per-frame recognition is noisy. These turn it into stable arrival/departure
# events — see presence.py.
FACE_CONFIRM_FRAMES: int = int(os.getenv("FACE_CONFIRM_FRAMES", "3"))
FACE_FORGET_FRAMES: int = int(os.getenv("FACE_FORGET_FRAMES", "5"))

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
# Webcam index for cv2.VideoCapture during development. On the Pi, Picamera2 is
# used instead and this is ignored.
CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))

# Frames per second the vision loop targets. Recognition is the expensive half;
# keeping this low leaves CPU for speech and the language model.
VISION_FPS: float = float(os.getenv("VISION_FPS", "5"))

# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------
# Capture is on a timer, not a keypress — the preview window does not reliably
# hold keyboard focus, and the robot has no keyboard. Samples are spaced so the
# student shifts between them; six identical frames enrol a single pose.
ENROLL_SAMPLES: int = int(os.getenv("ENROLL_SAMPLES", "6"))
ENROLL_INTERVAL: float = float(os.getenv("ENROLL_INTERVAL", "1.5"))
ENROLL_LEAD_IN: float = float(os.getenv("ENROLL_LEAD_IN", "3.0"))
ENROLL_TIMEOUT: float = float(os.getenv("ENROLL_TIMEOUT", "90.0"))
