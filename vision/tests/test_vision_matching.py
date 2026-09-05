"""
vision/tests/test_vision_matching.py — Unit tests for face embedding matching.

These run without a camera or an ONNX model: matching is pure vector maths,
so we feed it synthetic embeddings.

Run with: pytest vision/tests/test_vision_matching.py -v
"""

import numpy as np
import pytest

from vision.matching import cosine_similarity, match_embedding
from vision.models import EnrolledFace


def _vec(*values: float) -> np.ndarray:
    """Build a float32 embedding from the given values."""
    return np.array(values, dtype=np.float32)


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        v = _vec(1.0, 2.0, 3.0)
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self):
        assert cosine_similarity(_vec(1.0, 0.0), _vec(0.0, 1.0)) == pytest.approx(0.0)

    def test_opposite_vectors_score_minus_one(self):
        assert cosine_similarity(_vec(1.0, 0.0), _vec(-1.0, 0.0)) == pytest.approx(-1.0)

    def test_magnitude_does_not_affect_score(self):
        """Cosine compares direction only — a 10x longer vector is still a match."""
        assert cosine_similarity(_vec(1.0, 1.0), _vec(10.0, 10.0)) == pytest.approx(1.0)

    def test_zero_vector_scores_zero_instead_of_dividing_by_zero(self):
        assert cosine_similarity(_vec(0.0, 0.0), _vec(1.0, 1.0)) == pytest.approx(0.0)


class TestMatchEmbedding:
    def test_empty_gallery_returns_no_match(self):
        result = match_embedding(_vec(1.0, 0.0), [], threshold=0.45)
        assert result.student_id is None
        assert result.score == pytest.approx(0.0)

    def test_exact_match_returns_that_student(self):
        gallery = [EnrolledFace(student_id="asha", embeddings=[_vec(1.0, 0.0)])]
        result = match_embedding(_vec(1.0, 0.0), gallery, threshold=0.45)
        assert result.student_id == "asha"
        assert result.score == pytest.approx(1.0)

    def test_score_below_threshold_returns_unknown(self):
        """A stranger must come back as unknown, not as the nearest student."""
        gallery = [EnrolledFace(student_id="asha", embeddings=[_vec(1.0, 0.0)])]
        result = match_embedding(_vec(0.0, 1.0), gallery, threshold=0.45)
        assert result.student_id is None

    def test_unknown_still_reports_the_best_score_for_debugging(self):
        gallery = [EnrolledFace(student_id="asha", embeddings=[_vec(1.0, 0.0)])]
        result = match_embedding(_vec(1.0, 1.0), gallery, threshold=0.95)
        assert result.student_id is None
        assert result.score == pytest.approx(0.7071, abs=1e-3)

    def test_picks_the_highest_scoring_student(self):
        gallery = [
            EnrolledFace(student_id="asha", embeddings=[_vec(1.0, 0.0)]),
            EnrolledFace(student_id="ravi", embeddings=[_vec(0.9, 0.1)]),
        ]
        result = match_embedding(_vec(0.9, 0.1), gallery, threshold=0.45)
        assert result.student_id == "ravi"

    def test_uses_best_of_a_students_multiple_embeddings(self):
        """
        Enrolment stores several embeddings per student (different poses/lighting).
        A probe matching ANY one of them should identify the student.
        """
        gallery = [
            EnrolledFace(
                student_id="asha",
                embeddings=[_vec(1.0, 0.0), _vec(0.0, 1.0)],
            )
        ]
        result = match_embedding(_vec(0.0, 1.0), gallery, threshold=0.45)
        assert result.student_id == "asha"
        assert result.score == pytest.approx(1.0)

    def test_rejects_probe_of_wrong_dimension(self):
        gallery = [EnrolledFace(student_id="asha", embeddings=[_vec(1.0, 0.0)])]
        with pytest.raises(ValueError):
            match_embedding(_vec(1.0, 0.0, 3.0), gallery, threshold=0.45)
