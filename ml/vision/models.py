"""
vision/models.py — Data types for the vision pipeline.

Two families live here:

  * Internal types (dataclasses) carry numpy arrays between pipeline stages.
    Pydantic is deliberately avoided for these — validating a 128-float
    vector on every camera frame is wasted CPU on a Raspberry Pi.

  * API types (pydantic) are the request/response shapes exposed by FastAPI,
    where validation is worth paying for because the input is untrusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Internal pipeline types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceBox:
    """
    One detected face in a frame.

    YuNet returns a bounding box, five facial landmarks (right eye, left eye,
    nose tip, right mouth corner, left mouth corner) and a confidence score.
    The landmarks matter: SFace uses them to rotate and crop the face to a
    canonical position before embedding it. Skipping that alignment step is
    the single most common reason face recognition accuracy is poor.
    """

    x: int
    y: int
    width: int
    height: int
    score: float
    # Raw 15-element row YuNet produced, kept so SFace can align from it.
    raw: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def area(self) -> int:
        """Pixel area — used to pick the closest (largest) face at the desk."""
        return self.width * self.height


@dataclass(frozen=True)
class EnrolledFace:
    """
    One enrolled student and every embedding captured for them.

    Several embeddings per student is deliberate: enrolment samples a few
    frames across slightly different poses and lighting, and a probe matching
    ANY of them identifies the student. Averaging them into a single centroid
    would discard exactly the variation that makes desk lighting survivable.
    """

    student_id: str
    embeddings: list[np.ndarray]


@dataclass(frozen=True)
class MatchResult:
    """
    Outcome of comparing one probe embedding against the enrolled gallery.

    ``student_id`` is None when nothing cleared the threshold. ``score`` is
    always the best similarity seen, even on a miss, so a near-miss can be
    debugged without turning the threshold down blindly.
    """

    student_id: Optional[str]
    score: float

    @property
    def is_match(self) -> bool:
        return self.student_id is not None


# ---------------------------------------------------------------------------
# API types
# ---------------------------------------------------------------------------


class FaceBoxOut(BaseModel):
    """A detected face, as returned over HTTP."""

    x: int
    y: int
    width: int
    height: int
    score: float = Field(..., description="Detector confidence, 0.0 - 1.0")


class DetectionResponse(BaseModel):
    """Result of running detection only (no identification)."""

    face_count: int
    faces: list[FaceBoxOut]


class IdentifyResponse(BaseModel):
    """Result of detecting and then identifying the largest face in a frame."""

    face_count: int
    student_id: Optional[str] = Field(
        None, description="Matched student, or null when nobody cleared the threshold"
    )
    score: float = Field(0.0, description="Best similarity score seen, matched or not")
    face: Optional[FaceBoxOut] = None


class EnrollResponse(BaseModel):
    """Result of enrolling one or more frames for a student."""

    student_id: str
    embeddings_added: int
    embeddings_total: int
    frames_rejected: int = Field(
        0, description="Frames skipped because no usable face was found"
    )
