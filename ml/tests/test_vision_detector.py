"""
tests/test_vision_detector.py — Tests for YuNet face detection.

Run with: pytest tests/test_vision_detector.py -v
"""

import numpy as np
import pytest

from tests.conftest import DETECTOR_MODEL, requires_models
from vision.detector import DEFAULT_DETECT_THRESHOLD, FaceDetector

pytestmark = requires_models


@pytest.fixture
def detector():
    return FaceDetector(DETECTOR_MODEL)


class TestLoading:
    def test_missing_model_file_fails_with_a_useful_message(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="download_models"):
            FaceDetector(tmp_path / "not_here.onnx")


class TestDetection:
    def test_finds_the_face_in_a_photograph(self, detector, face_image):
        faces = detector.detect(face_image)
        assert len(faces) == 1

    def test_reports_high_confidence_on_a_clear_face(self, detector, face_image):
        assert detector.detect(face_image)[0].score > 0.9

    def test_box_lies_inside_the_frame(self, detector, face_image):
        height, width = face_image.shape[:2]
        face = detector.detect(face_image)[0]
        assert 0 <= face.x and 0 <= face.y
        assert face.x + face.width <= width
        assert face.y + face.height <= height

    def test_keeps_the_landmarks_needed_for_alignment(self, detector, face_image):
        """
        YuNet's row is [x, y, w, h, 10 landmark values, score]. SFace needs
        that whole row to align the crop, so it must survive detection.
        """
        face = detector.detect(face_image)[0]
        assert face.raw is not None
        assert face.raw.shape == (15,)

    def test_finds_nothing_in_a_blank_frame(self, detector, blank_image):
        assert detector.detect(blank_image) == []

    def test_does_not_hallucinate_faces_in_a_star_field(self, detector, faceless_image):
        """
        The default threshold of 0.9 exists for this reason: at 0.5 this image
        yields three phantom 'faces'. A companion robot must not greet a bookshelf.
        """
        assert detector.detect(faceless_image) == []

    def test_a_lax_threshold_does_hallucinate(self, faceless_image):
        """Pins why the threshold is not a free parameter to lower casually."""
        lax = FaceDetector(DETECTOR_MODEL, score_threshold=0.5)
        assert len(lax.detect(faceless_image)) > 0


class TestFrameSizeHandling:
    def test_handles_a_change_in_frame_size(self, detector, face_image, blank_image):
        """
        YuNet must be told the input size before every detect() call. Forgetting
        to update it after a resolution change is the classic YuNet bug: it
        silently returns garbage boxes instead of raising.
        """
        assert len(detector.detect(face_image)) == 1       # 512x512
        assert detector.detect(blank_image) == []          # 640x480
        assert len(detector.detect(face_image)) == 1       # 512x512 again

    def test_detects_the_same_face_after_the_frame_is_resized(self, detector, face_image):
        small = np.ascontiguousarray(face_image[::2, ::2])
        assert len(detector.detect(small)) == 1


class TestLargestFace:
    def test_returns_none_when_nobody_is_there(self, detector, blank_image):
        assert detector.detect_largest(blank_image) is None

    def test_returns_the_face_when_one_person_is_there(self, detector, face_image):
        assert detector.detect_largest(face_image) is not None

    def test_prefers_the_nearest_face_when_two_people_are_in_frame(
        self, detector, face_image, other_face_image
    ):
        """
        The student at the desk is the closest face, which means the largest
        box. A sibling standing behind must not hijack the session.
        """
        big = face_image
        small = np.ascontiguousarray(other_face_image[::2, ::2])
        canvas = np.zeros((512, 512 + small.shape[1], 3), dtype=np.uint8)
        canvas[: big.shape[0], : big.shape[1]] = big
        canvas[: small.shape[0], big.shape[1] :] = small

        lax = FaceDetector(DETECTOR_MODEL, score_threshold=0.5)
        all_faces = lax.detect(canvas)
        largest = lax.detect_largest(canvas)

        assert len(all_faces) >= 2
        assert largest.area == max(f.area for f in all_faces)


class TestThresholdCalibration:
    """
    The detector threshold is the one number that decides whether the robot
    sees the student. It is bracketed from both sides by measurement, so it
    cannot drift in either direction without a test failing.

    Measured on 225 live webcam frames of a person moving normally:

        face found by the detector    225/225 frames (100%)
        median confidence             0.833
        frames scoring >= 0.90         18%   <- too strict, drops out on movement
        frames scoring >= 0.70         60%

    Measured on images containing no faces at all:

        highest false-positive score  0.585  (a star field)

    So the usable range is roughly 0.59 to 0.83, and the default sits at 0.70.
    """

    def test_default_is_strict_enough_to_reject_every_faceless_image(
        self, detector, faceless_images
    ):
        """Guards the lower bound: below ~0.59 the star field creates phantoms."""
        for name, image in faceless_images.items():
            assert detector.detect(image) == [], f"hallucinated a face in {name}"

    def test_default_is_loose_enough_to_hold_a_moving_face(self):
        """
        Guards the upper bound.

        A real face is reported at around 0.83 while the student moves, dipping
        well below that mid-motion. A threshold at 0.9 discarded 82% of frames
        in which the detector had, in fact, found the face — which reads as the
        robot losing track of the student every time they shift in their chair.
        """
        assert DEFAULT_DETECT_THRESHOLD <= 0.75

    def test_config_default_matches_the_detector_default(self):
        """The two must not drift apart; config.py is what actually ships."""
        import config

        assert config.FACE_DETECT_THRESHOLD == DEFAULT_DETECT_THRESHOLD
