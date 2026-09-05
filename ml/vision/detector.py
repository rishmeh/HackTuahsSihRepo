"""
vision/detector.py — Face detection with YuNet.

YuNet is a ~230 KB convolutional detector from OpenCV Zoo. It is pretrained:
nothing here learns anything. Given a frame it returns, for each face, a
bounding box, five landmarks (right eye, left eye, nose tip, right mouth
corner, left mouth corner) and a confidence score.

The landmarks are the reason we use this detector rather than a plain box
detector — SFace uses them to rotate and scale the face into a canonical
112x112 crop before embedding it. Recognition accuracy collapses without
that alignment step.

Two details of the OpenCV API that are easy to get wrong, and are pinned by
tests in tests/test_vision_detector.py:

  1. ``detect`` returns None, not an empty array, when there are no faces.
  2. The detector carries an input size that must match the frame. Change
     resolution without updating it and YuNet returns wrong boxes silently
     rather than raising.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from vision.models import FaceBox

logger = logging.getLogger(__name__)

# Minimum confidence for a detection to count as a face.
#
# Calibrated from measurement, not taste. On 225 live webcam frames of a person
# moving normally the detector found the face in every single frame, but the
# confidence it reported had a median of 0.833 and dipped far lower mid-motion.
# At 0.9 that discarded 82% of good detections, which looks exactly like the
# robot losing track of the student whenever they shift in their chair.
#
# The floor comes from the other side: across images containing no faces, the
# highest false positive scored 0.585 (a star field). Anything below about 0.59
# starts inventing faces in textures.
#
# 0.70 sits between the two, with margin on both sides.
DEFAULT_DETECT_THRESHOLD = 0.70


class FaceDetector:
    """
    Wraps ``cv2.FaceDetectorYN`` behind a frame-in, FaceBox-list-out interface.

    Args:
        model_path: Path to face_detection_yunet_2023mar.onnx.
        score_threshold: Minimum confidence to accept a detection. See
            DEFAULT_DETECT_THRESHOLD above for how the default was calibrated;
            below about 0.59 the detector starts finding "faces" in star fields
            and patterned bookshelves.
        nms_threshold: Overlap above which two boxes are merged as one face.
        top_k: Cap on candidate boxes considered before non-max suppression.
    """

    def __init__(
        self,
        model_path: str | Path,
        score_threshold: float = DEFAULT_DETECT_THRESHOLD,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ) -> None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"YuNet model not found at {model_path}. "
                "Fetch it with: python -m vision.download_models"
            )

        self.model_path = model_path
        self.score_threshold = score_threshold
        self._input_size: tuple[int, int] = (320, 320)

        self._detector = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            self._input_size,
            score_threshold,
            nms_threshold,
            top_k,
        )
        logger.info("YuNet loaded from %s (threshold=%.2f)", model_path, score_threshold)

    def detect(self, frame: np.ndarray) -> list[FaceBox]:
        """
        Find every face in a BGR frame, largest first.

        Sorting by size means index 0 is the nearest person — the one sitting
        at the desk rather than someone walking past behind them.
        """
        if frame is None or frame.size == 0:
            return []

        height, width = frame.shape[:2]
        if (width, height) != self._input_size:
            # Must happen before every detect on a new resolution, or YuNet
            # scales the boxes against stale dimensions.
            self._detector.setInputSize((width, height))
            self._input_size = (width, height)

        _, raw_faces = self._detector.detect(frame)
        if raw_faces is None:
            return []

        faces = [_to_face_box(row) for row in raw_faces]
        faces.sort(key=lambda f: f.area, reverse=True)
        return faces

    def detect_largest(self, frame: np.ndarray) -> FaceBox | None:
        """
        The nearest face in the frame, or None if there is nobody there.

        This is the entry point the session loop uses: Table Tot cares about
        the one student at the desk, not everyone in the room.
        """
        faces = self.detect(frame)
        return faces[0] if faces else None


def _to_face_box(row: np.ndarray) -> FaceBox:
    """
    Convert one YuNet output row into a FaceBox.

    Row layout is 15 floats: x, y, w, h, then five (x, y) landmark pairs,
    then the confidence score. The whole row is kept in ``raw`` because
    SFace's alignCrop needs the landmarks, not just the box.
    """
    row = np.asarray(row, dtype=np.float32).ravel()
    x, y, width, height = (int(round(v)) for v in row[:4])
    return FaceBox(
        x=max(0, x),
        y=max(0, y),
        width=width,
        height=height,
        score=float(row[14]),
        raw=row,
    )
