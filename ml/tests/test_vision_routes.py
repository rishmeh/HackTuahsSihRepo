"""
tests/test_vision_routes.py — Tests for the face HTTP endpoints.

The router is mounted on a throwaway FastAPI app with a pipeline pointed at a
temporary database, so these exercise the real models and real request parsing
without touching the developer's enrolled faces.

Run with: pytest tests/test_vision_routes.py -v
"""

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import DETECTOR_MODEL, RECOGNIZER_MODEL, requires_models
from vision.detector import FaceDetector
from vision.face_store import FaceStore
from vision.pipeline import VisionPipeline
from vision.recognizer import FaceRecognizer
from vision.routes import get_pipeline, router

pytestmark = requires_models


@pytest.fixture
def pipeline(tmp_path):
    return VisionPipeline(
        detector=FaceDetector(DETECTOR_MODEL, score_threshold=0.5),
        recognizer=FaceRecognizer(RECOGNIZER_MODEL),
        store=FaceStore(tmp_path / "faces.db"),
    )


@pytest.fixture
def client(pipeline):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    return TestClient(app)


def _png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


def _upload(image: np.ndarray, name: str = "frame.png"):
    return ("images", (name, _png(image), "image/png"))


class TestDetectEndpoint:
    def test_reports_the_face_in_an_uploaded_photo(self, client, face_image):
        response = client.post(
            "/vision/face/detect", files=[("image", ("f.png", _png(face_image), "image/png"))]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["face_count"] == 1
        assert body["faces"][0]["score"] > 0.5

    def test_reports_nothing_for_an_empty_frame(self, client, blank_image):
        response = client.post(
            "/vision/face/detect",
            files=[("image", ("f.png", _png(blank_image), "image/png"))],
        )
        assert response.json()["face_count"] == 0

    def test_rejects_a_file_that_is_not_an_image(self, client):
        response = client.post(
            "/vision/face/detect",
            files=[("image", ("notes.txt", b"this is not a picture", "text/plain"))],
        )
        assert response.status_code == 422


class TestEnrollEndpoint:
    def test_enrolls_a_student_from_uploaded_frames(self, client, face_image):
        response = client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image), _upload(cv2.flip(face_image, 1), "b.png")],
        )
        assert response.status_code == 200
        body = response.json()
        assert body["student_id"] == "asha"
        assert body["embeddings_added"] == 2

    def test_counts_frames_that_had_no_face(self, client, face_image, blank_image):
        response = client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image), _upload(blank_image, "blank.png")],
        )
        assert response.json()["frames_rejected"] == 1

    def test_rejects_an_enrolment_with_no_usable_face(self, client, blank_image):
        response = client.post(
            "/vision/face/enroll",
            data={"student_id": "ghost"},
            files=[_upload(blank_image)],
        )
        assert response.status_code == 422
        assert "no face" in response.json()["detail"]


class TestIdentifyEndpoint:
    def test_identifies_an_enrolled_student(self, client, face_image):
        client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image), _upload(cv2.flip(face_image, 1), "b.png")],
        )
        response = client.post(
            "/vision/face/identify",
            files=[("image", ("f.png", _png(face_image), "image/png"))],
        )
        assert response.status_code == 200
        assert response.json()["student_id"] == "asha"

    def test_returns_unknown_for_a_stranger(self, client, face_image, other_face_image):
        client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image)],
        )
        response = client.post(
            "/vision/face/identify",
            files=[("image", ("f.png", _png(other_face_image), "image/png"))],
        )
        assert response.json()["student_id"] is None

    def test_distinguishes_no_face_from_an_unknown_face(self, client, blank_image):
        response = client.post(
            "/vision/face/identify",
            files=[("image", ("f.png", _png(blank_image), "image/png"))],
        )
        body = response.json()
        assert body["face_count"] == 0
        assert body["student_id"] is None


class TestStudentManagement:
    def test_lists_enrolled_students(self, client, face_image):
        client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image)],
        )
        response = client.get("/vision/face/students")
        assert response.status_code == 200
        assert response.json()["students"] == ["asha"]

    def test_deletes_a_student(self, client, face_image):
        client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image)],
        )
        response = client.delete("/vision/face/students/asha")
        assert response.status_code == 200
        assert response.json()["embeddings_removed"] == 1
        assert client.get("/vision/face/students").json()["students"] == []

    def test_a_deleted_student_is_no_longer_recognised(self, client, face_image):
        """Erasure must take effect immediately, not after a restart."""
        client.post(
            "/vision/face/enroll",
            data={"student_id": "asha"},
            files=[_upload(face_image)],
        )
        client.delete("/vision/face/students/asha")
        response = client.post(
            "/vision/face/identify",
            files=[("image", ("f.png", _png(face_image), "image/png"))],
        )
        assert response.json()["student_id"] is None
