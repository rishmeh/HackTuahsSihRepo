"""
vision/pipeline.py — Orchestrates detection, recognition, storage and smoothing.

  frame
    │
    ▼
  [detector]   YuNet  → largest face + landmarks
    │
    ▼
  [recognizer] SFace  → 128-d embedding
    │
    ▼
  [matching]          → best gallery match, or unknown
    │
    ▼
  [presence]          → "arrived" / "departed", once the answer is stable

Mirrors the shape of chat/pipeline.py and quiz/generator.py: the components
are injected, so each can be tested alone and swapped later without touching
the callers.

The gallery is held in memory and refreshed on enrolment, so a frame never
causes a disk read. On a Pi that matters — this loop runs alongside speech
recognition and the language model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from vision.detector import FaceDetector
from vision.face_store import FaceStore
from vision.matching import match_embedding
from vision.models import FaceBox
from vision.presence import PresenceEvent, PresenceTracker
from vision.recognizer import DEFAULT_MATCH_THRESHOLD, FaceRecognizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IdentifyResult:
    """Who, if anyone, was recognised in a single frame."""

    face_count: int
    student_id: Optional[str]
    score: float
    face: Optional[FaceBox] = None


@dataclass(frozen=True)
class EnrollResult:
    """Outcome of enrolling a batch of frames for one student."""

    student_id: str
    embeddings_added: int
    embeddings_total: int
    frames_rejected: int


class VisionPipeline:
    """
    The full face pipeline, from camera frame to a confirmed student identity.

    Args:
        detector: Loaded YuNet detector.
        recognizer: Loaded SFace recognizer.
        store: Where enrolled embeddings live.
        threshold: Cosine similarity required to accept an identity.
        confirm_frames: Consecutive agreeing frames before announcing arrival.
        forget_frames: Consecutive empty frames before announcing departure.
    """

    def __init__(
        self,
        detector: FaceDetector,
        recognizer: FaceRecognizer,
        store: FaceStore,
        threshold: float = DEFAULT_MATCH_THRESHOLD,
        confirm_frames: int = 3,
        forget_frames: int = 5,
    ) -> None:
        self.detector = detector
        self.recognizer = recognizer
        self.store = store
        self.threshold = threshold
        self.tracker = PresenceTracker(
            confirm_frames=confirm_frames, forget_frames=forget_frames
        )
        self._gallery = store.load_gallery()
        logger.info(
            "Vision pipeline ready | %d student(s) enrolled | threshold=%.2f",
            len(self._gallery),
            threshold,
        )

    # -- enrolment ----------------------------------------------------------

    def enroll(self, student_id: str, frames: list[np.ndarray]) -> EnrollResult:
        """
        Teach the robot a new face from several frames.

        Frames without a detectable face are counted and skipped rather than
        failing the whole batch — during a live capture some frames are always
        blurred or mid-blink.

        Raises:
            ValueError: If not a single frame contained a usable face.
        """
        embeddings: list[np.ndarray] = []
        rejected = 0

        for frame in frames:
            face = self.detector.detect_largest(frame)
            if face is None:
                rejected += 1
                continue
            embeddings.append(self.recognizer.embed(frame, face))

        if not embeddings:
            raise ValueError(
                f"no face found in any of the {len(frames)} frame(s) for "
                f"student {student_id!r} — check lighting and camera framing"
            )

        added = self.store.add_embeddings(student_id, embeddings)
        self.reload_gallery()

        return EnrollResult(
            student_id=student_id,
            embeddings_added=added,
            embeddings_total=self.store.count_embeddings(student_id),
            frames_rejected=rejected,
        )

    def reload_gallery(self) -> None:
        """Re-read enrolled embeddings from disk into memory."""
        self._gallery = self.store.load_gallery()

    # -- recognition --------------------------------------------------------

    def identify(self, frame: np.ndarray) -> IdentifyResult:
        """
        Identify the nearest face in one frame. Stateless — no smoothing.

        Returns a result with ``student_id`` None both when there is no face
        and when the face belongs to nobody enrolled; ``face_count``
        distinguishes the two.
        """
        faces = self.detector.detect(frame)
        if not faces:
            return IdentifyResult(face_count=0, student_id=None, score=0.0)

        nearest = faces[0]
        embedding = self.recognizer.embed(frame, nearest)
        match = match_embedding(embedding, self._gallery, self.threshold)

        return IdentifyResult(
            face_count=len(faces),
            student_id=match.student_id,
            score=match.score,
            face=nearest,
        )

    def process_frame(self, frame: np.ndarray) -> Optional[PresenceEvent]:
        """
        Identify one frame and fold it into the presence state machine.

        This is what the camera loop calls. It returns an event only on the
        frame where presence actually changes, so the caller can drive persona
        loading and the greeting without debouncing anything itself.
        """
        return self.tracker.update(self.identify(frame).student_id)

    @property
    def current_student(self) -> Optional[str]:
        """The student confirmed to be at the desk right now, or None."""
        return self.tracker.current

    @property
    def enrolled_students(self) -> list[str]:
        """Every student id known to the robot."""
        return [face.student_id for face in self._gallery]
