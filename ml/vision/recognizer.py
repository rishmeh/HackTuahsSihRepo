"""
vision/recognizer.py — Face embedding with SFace.

SFace is a ~38 MB pretrained network from OpenCV Zoo. It does not classify
students — it has never seen them. What it does is map any aligned face crop
into a 128-dimensional vector, trained so that two crops of the same person
land close together and two crops of different people land far apart.

That is what makes enrolment cheap: adding a student is storing a handful of
vectors, not retraining anything. Recognition is then a nearest-neighbour
lookup, which is why this scales to a family on a Raspberry Pi.

Measured on the test fixtures (two different real people):

    same person, mirrored     0.944
    same person, brightened   0.99
    different people          0.198

DEFAULT_MATCH_THRESHOLD sits at 0.45 in that gap. OpenCV's own published
figure is 0.363, tuned for balanced accuracy on benchmarks; ours is stricter
on purpose. A false reject costs one spoken "who are you?"; a false accept
silently loads another student's persona, progress and revision queue.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from vision.models import FaceBox

logger = logging.getLogger(__name__)

# Cosine similarity above which two embeddings are treated as the same person.
DEFAULT_MATCH_THRESHOLD = 0.45

# SFace consumes a 112x112 aligned crop and emits 128 numbers.
EMBEDDING_DIM = 128


class FaceRecognizer:
    """
    Wraps ``cv2.FaceRecognizerSF`` behind a (frame, FaceBox) -> embedding call.

    Args:
        model_path: Path to face_recognition_sface_2021dec.onnx.
    """

    def __init__(self, model_path: str | Path) -> None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"SFace model not found at {model_path}. "
                "Fetch it with: python -m vision.download_models"
            )

        self.model_path = model_path
        self._recognizer = cv2.FaceRecognizerSF.create(str(model_path), "")
        logger.info("SFace loaded from %s", model_path)

    def embed(self, frame: np.ndarray, face: FaceBox) -> np.ndarray:
        """
        Turn one detected face into its 128-d embedding.

        Alignment happens first: ``alignCrop`` uses the five landmarks to
        rotate and scale the face to a canonical 112x112 position, so a head
        tilted 15 degrees produces nearly the same vector as an upright one.
        Cropping the raw bounding box instead — the common shortcut — costs a
        large amount of accuracy.

        Raises:
            ValueError: If the FaceBox carries no landmark row.
        """
        if face.raw is None:
            raise ValueError(
                "FaceBox has no landmark data; SFace needs YuNet's full 15-value "
                "row to align the crop. Pass a FaceBox produced by FaceDetector."
            )

        aligned = self._recognizer.alignCrop(frame, face.raw.reshape(1, -1))
        # OpenCV returns shape (1, 128); flatten so the store and matcher see
        # a plain 128-vector.
        embedding = self._recognizer.feature(aligned).ravel()
        return np.ascontiguousarray(embedding, dtype=np.float32)
