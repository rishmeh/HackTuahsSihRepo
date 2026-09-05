"""
vision/matching.py — Comparing face embeddings.

SFace turns an aligned face crop into a 128-dimensional vector. Two vectors
from the same person point in a similar direction; two from different people
do not. "Similar direction" is measured with cosine similarity, which ignores
vector length and looks only at angle — so brightness changes that scale the
whole vector do not move the score.

This module is pure maths: no camera, no ONNX, no I/O. That is what makes the
identity logic testable without hardware.
"""

from __future__ import annotations

import numpy as np

from vision.models import EnrolledFace, MatchResult


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine of the angle between two vectors, in the range -1.0 to 1.0.

    1.0 means identical direction (same face), 0.0 means unrelated, and
    negative means opposed. A zero-length vector has no direction at all,
    so it scores 0.0 rather than raising a divide-by-zero.
    """
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()

    if a.shape != b.shape:
        raise ValueError(
            f"embedding dimension mismatch: probe has {a.shape[0]}, "
            f"gallery entry has {b.shape[0]}"
        )

    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0

    return float(np.dot(a, b) / denominator)


def match_embedding(
    probe: np.ndarray,
    gallery: list[EnrolledFace],
    threshold: float,
) -> MatchResult:
    """
    Find which enrolled student, if any, the probe embedding belongs to.

    Scores the probe against every embedding of every student and keeps the
    single best. The winner is returned only if it clears ``threshold`` —
    otherwise the result is "unknown", which the caller should handle by
    asking the student who they are rather than guessing.

    Raises:
        ValueError: If the probe's dimension does not match the gallery's.
    """
    best_id: str | None = None
    best_score = 0.0

    for enrolled in gallery:
        for candidate in enrolled.embeddings:
            score = cosine_similarity(probe, candidate)
            if score > best_score:
                best_score = score
                best_id = enrolled.student_id

    if best_score < threshold:
        return MatchResult(student_id=None, score=best_score)

    return MatchResult(student_id=best_id, score=best_score)
