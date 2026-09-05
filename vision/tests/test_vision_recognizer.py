"""
vision/tests/test_vision_recognizer.py — Tests for SFace face recognition.

These use photographs of two different real people, so the same-person and
different-person claims are measured, not assumed.

Run with: pytest vision/tests/test_vision_recognizer.py -v
"""

import cv2
import numpy as np
import pytest

from vision.tests.conftest import DETECTOR_MODEL, RECOGNIZER_MODEL, requires_models
from vision.detector import FaceDetector
from vision.matching import cosine_similarity
from vision.models import FaceBox
from vision.recognizer import DEFAULT_MATCH_THRESHOLD, FaceRecognizer

pytestmark = requires_models


@pytest.fixture
def detector():
    return FaceDetector(DETECTOR_MODEL, score_threshold=0.5)


@pytest.fixture
def recognizer():
    return FaceRecognizer(RECOGNIZER_MODEL)


def _embed(detector, recognizer, image):
    face = detector.detect_largest(image)
    assert face is not None, "fixture image should contain a detectable face"
    return recognizer.embed(image, face)


class TestLoading:
    def test_missing_model_file_fails_with_a_useful_message(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="download_models"):
            FaceRecognizer(tmp_path / "not_here.onnx")


class TestEmbedding:
    def test_embedding_is_a_flat_128_vector(self, detector, recognizer, face_image):
        """
        OpenCV hands back shape (1, 128). Everything downstream — the store,
        the matcher — expects (128,), so the wrapper must flatten it.
        """
        embedding = _embed(detector, recognizer, face_image)
        assert embedding.shape == (128,)

    def test_embedding_is_float32(self, detector, recognizer, face_image):
        assert _embed(detector, recognizer, face_image).dtype == np.float32

    def test_embedding_is_deterministic(self, detector, recognizer, face_image):
        first = _embed(detector, recognizer, face_image)
        second = _embed(detector, recognizer, face_image)
        np.testing.assert_array_equal(first, second)

    def test_needs_landmarks_to_align_the_crop(self, recognizer, face_image):
        """A box without YuNet's landmark row cannot be aligned, so refuse it."""
        boxless = FaceBox(x=10, y=10, width=50, height=50, score=0.99, raw=None)
        with pytest.raises(ValueError, match="landmark"):
            recognizer.embed(face_image, boxless)


class TestIdentityDiscrimination:
    def test_the_same_person_scores_high(self, detector, recognizer, face_image):
        """Mirroring changes every pixel but not the identity."""
        original = _embed(detector, recognizer, face_image)
        mirrored = _embed(detector, recognizer, cv2.flip(face_image, 1))
        assert cosine_similarity(original, mirrored) > 0.9

    def test_two_different_people_score_low(
        self, detector, recognizer, face_image, other_face_image
    ):
        person_a = _embed(detector, recognizer, face_image)
        person_b = _embed(detector, recognizer, other_face_image)
        assert cosine_similarity(person_a, person_b) < 0.3

    def test_the_default_threshold_separates_them(
        self, detector, recognizer, face_image, other_face_image
    ):
        """
        The whole design rests on one number. Same-person scores must land
        above it and different-person scores below it, with room to spare.
        """
        person_a = _embed(detector, recognizer, face_image)
        same_person = _embed(detector, recognizer, cv2.flip(face_image, 1))
        person_b = _embed(detector, recognizer, other_face_image)

        assert cosine_similarity(person_a, same_person) > DEFAULT_MATCH_THRESHOLD
        assert cosine_similarity(person_a, person_b) < DEFAULT_MATCH_THRESHOLD

    def test_identity_survives_a_brightness_change(
        self, detector, recognizer, face_image
    ):
        """Desk lamp on or off must not change who the student is."""
        bright = cv2.convertScaleAbs(face_image, alpha=1.0, beta=40)
        original = _embed(detector, recognizer, face_image)
        lit = _embed(detector, recognizer, bright)
        assert cosine_similarity(original, lit) > DEFAULT_MATCH_THRESHOLD
