"""
vision/factory.py — Builds a configured VisionPipeline from config.py.

Kept separate from pipeline.py so the pipeline itself stays free of global
configuration and remains easy to construct with test doubles.
"""

from __future__ import annotations

import logging

from vision import config
from vision.detector import FaceDetector
from vision.face_store import FaceStore
from vision.pipeline import VisionPipeline
from vision.recognizer import FaceRecognizer

logger = logging.getLogger(__name__)


def build_pipeline() -> VisionPipeline:
    """
    Construct the pipeline using the paths and thresholds in config.py.

    Loading the models takes a second or two, so build this once at start-up
    and reuse it, rather than per request.
    """
    return VisionPipeline(
        detector=FaceDetector(
            config.YUNET_MODEL_PATH,
            score_threshold=config.FACE_DETECT_THRESHOLD,
        ),
        recognizer=FaceRecognizer(config.SFACE_MODEL_PATH),
        store=FaceStore(config.FACE_DB_PATH),
        threshold=config.FACE_MATCH_THRESHOLD,
        confirm_frames=config.FACE_CONFIRM_FRAMES,
        forget_frames=config.FACE_FORGET_FRAMES,
    )
