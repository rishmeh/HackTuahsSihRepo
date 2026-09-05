"""
tests/test_vision_pipeline.py — End-to-end tests for the vision pipeline.

Real ONNX models, real photographs, a real SQLite file. Only the camera is
absent. This is the test that answers "would the demo work?".

Run with: pytest tests/test_vision_pipeline.py -v
"""

import cv2
import numpy as np
import pytest

from tests.conftest import DETECTOR_MODEL, RECOGNIZER_MODEL, requires_models
from vision.detector import FaceDetector
from vision.face_store import FaceStore
from vision.pipeline import VisionPipeline
from vision.presence import PresenceEvent
from vision.recognizer import FaceRecognizer

pytestmark = requires_models


@pytest.fixture
def pipeline(tmp_path):
    return VisionPipeline(
        detector=FaceDetector(DETECTOR_MODEL, score_threshold=0.5),
        recognizer=FaceRecognizer(RECOGNIZER_MODEL),
        store=FaceStore(tmp_path / "faces.db"),
        confirm_frames=3,
        forget_frames=5,
    )


def _variants(image: np.ndarray) -> list[np.ndarray]:
    """A few frames of one person, as enrolment would capture from a camera."""
    return [
        image,
        cv2.flip(image, 1),
        cv2.convertScaleAbs(image, alpha=1.0, beta=30),
        cv2.convertScaleAbs(image, alpha=0.9, beta=-20),
    ]


class TestEnrolment:
    def test_enrols_a_student_from_several_frames(self, pipeline, face_image):
        result = pipeline.enroll("asha", _variants(face_image))
        assert result.embeddings_added == 4
        assert result.frames_rejected == 0

    def test_skips_frames_with_no_face_in_them(self, pipeline, face_image, blank_image):
        result = pipeline.enroll("asha", [face_image, blank_image, blank_image])
        assert result.embeddings_added == 1
        assert result.frames_rejected == 2

    def test_refuses_to_enrol_a_student_with_no_usable_frame(
        self, pipeline, blank_image
    ):
        with pytest.raises(ValueError, match="no face"):
            pipeline.enroll("ghost", [blank_image, blank_image])

    def test_enrolling_again_adds_to_the_same_student(self, pipeline, face_image):
        pipeline.enroll("asha", [face_image])
        result = pipeline.enroll("asha", [cv2.flip(face_image, 1)])
        assert result.embeddings_total == 2


class TestIdentification:
    def test_recognises_an_enrolled_student(self, pipeline, face_image):
        pipeline.enroll("asha", _variants(face_image))
        result = pipeline.identify(face_image)
        assert result.student_id == "asha"
        assert result.score > 0.45

    def test_a_stranger_is_reported_as_unknown_not_as_the_nearest_student(
        self, pipeline, face_image, other_face_image
    ):
        """The safety-critical case: a sibling must not inherit Asha's session."""
        pipeline.enroll("asha", _variants(face_image))
        result = pipeline.identify(other_face_image)
        assert result.student_id is None

    def test_reports_no_face_on_an_empty_frame(self, pipeline, face_image, blank_image):
        pipeline.enroll("asha", _variants(face_image))
        result = pipeline.identify(blank_image)
        assert result.face_count == 0
        assert result.student_id is None

    def test_identification_works_without_a_manual_gallery_reload(
        self, pipeline, face_image
    ):
        """Enrolling must take effect immediately, not after a restart."""
        assert pipeline.identify(face_image).student_id is None
        pipeline.enroll("asha", [face_image])
        assert pipeline.identify(face_image).student_id == "asha"

    def test_a_student_enrolled_before_a_restart_is_still_known(
        self, tmp_path, face_image
    ):
        db = tmp_path / "faces.db"
        first = VisionPipeline(
            detector=FaceDetector(DETECTOR_MODEL, score_threshold=0.5),
            recognizer=FaceRecognizer(RECOGNIZER_MODEL),
            store=FaceStore(db),
        )
        first.enroll("asha", _variants(face_image))

        rebooted = VisionPipeline(
            detector=FaceDetector(DETECTOR_MODEL, score_threshold=0.5),
            recognizer=FaceRecognizer(RECOGNIZER_MODEL),
            store=FaceStore(db),
        )
        assert rebooted.identify(face_image).student_id == "asha"


class TestPresenceStream:
    def test_announces_arrival_only_after_enough_consistent_frames(
        self, pipeline, face_image
    ):
        pipeline.enroll("asha", _variants(face_image))
        assert pipeline.process_frame(face_image) is None
        assert pipeline.process_frame(face_image) is None
        assert pipeline.process_frame(face_image) == PresenceEvent(
            kind="arrived", student_id="asha"
        )

    def test_announces_departure_after_sustained_absence(self, pipeline, face_image, blank_image):
        pipeline.enroll("asha", _variants(face_image))
        for _ in range(3):
            pipeline.process_frame(face_image)

        event = None
        for _ in range(5):
            event = pipeline.process_frame(blank_image)
        assert event == PresenceEvent(kind="departed", student_id="asha")

    def test_current_student_tracks_who_is_at_the_desk(self, pipeline, face_image):
        pipeline.enroll("asha", _variants(face_image))
        assert pipeline.current_student is None
        for _ in range(3):
            pipeline.process_frame(face_image)
        assert pipeline.current_student == "asha"

    def test_an_unknown_face_never_becomes_the_current_student(
        self, pipeline, face_image, other_face_image
    ):
        pipeline.enroll("asha", _variants(face_image))
        for _ in range(10):
            pipeline.process_frame(other_face_image)
        assert pipeline.current_student is None
