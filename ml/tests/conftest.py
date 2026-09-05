"""
tests/conftest.py — Shared fixtures.

Vision tests need real face images but must not need a camera. scikit-image
ships photographs of two different real people, which gives us honest
same-person and different-person pairs offline and deterministically.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest
from skimage import data

# OpenCV 5's new graph engine logs a harmless "Targets are not supported"
# warning on every model load. Silence it so test output stays clean.
cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DETECTOR_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

_models_present = DETECTOR_MODEL.exists() and RECOGNIZER_MODEL.exists()
requires_models = pytest.mark.skipif(
    not _models_present,
    reason="ONNX models missing — run: python -m vision.download_models",
)


@pytest.fixture
def face_image() -> np.ndarray:
    """A photograph of person A, in OpenCV's BGR channel order."""
    return cv2.cvtColor(data.astronaut(), cv2.COLOR_RGB2BGR)


@pytest.fixture
def other_face_image() -> np.ndarray:
    """A photograph of a different person, person B, in BGR."""
    return cv2.cvtColor(data.camera(), cv2.COLOR_GRAY2BGR)


@pytest.fixture
def faceless_image() -> np.ndarray:
    """
    A star field: rich in bright blobs, containing no faces at all.

    A useful adversarial negative — a weak detector threshold hallucinates
    faces in it, which is exactly the failure this fixture guards against.
    """
    return cv2.cvtColor(data.hubble_deep_field(), cv2.COLOR_RGB2BGR)


@pytest.fixture
def blank_image() -> np.ndarray:
    """A plain black 640x480 frame — what the camera sees with the lens capped."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def faceless_images() -> dict[str, np.ndarray]:
    """
    Several images containing no faces, as BGR frames.

    A star field, a coffee cup, a cat and a gravel path. Between them they
    cover the textures that make weak detectors hallucinate: bright blobs on
    dark ground, and dense high-frequency noise.
    """
    images = {}
    for name in ("hubble_deep_field", "coffee", "chelsea", "gravel"):
        array = getattr(data, name)()
        images[name] = (
            cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)
            if array.ndim == 2
            else cv2.cvtColor(array[:, :, :3], cv2.COLOR_RGB2BGR)
        )
    return images
