"""
learner/tests/test_routes.py — Tests for the questionnaire HTTP endpoints.

This is the contract the student app builds against.

Run with: pytest learner/tests/test_routes.py -v
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from learner.profile_store import ProfileStore
from learner.routes import get_store, router


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    store = ProfileStore(tmp_path / "learner.db")
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


FULL_ANSWERS = {"1": "A", "2": "B", "3": "C", "4": "A", "5": "B",
                "6": "D", "7": "B", "8": "A", "9": "A", "10": "D"}


class TestQuestionnaire:
    def test_app_can_fetch_the_questionnaire(self, client):
        response = client.get("/learner/questionnaire")
        assert response.status_code == 200
        body = response.json()
        assert len(body["scenes"]) == 10
        assert body["scenes"][0]["options"][0]["key"] == "A"

    def test_questionnaire_response_has_no_scoring_data(self, client):
        text = client.get("/learner/questionnaire").text
        assert "weights" not in text
        assert "failure_sensitivity" not in text


class TestSubmitAnswers:
    def test_submitting_answers_returns_profile_and_settings(self, client):
        response = client.post("/learner/asha/answers", json={"age": 12, "answers": FULL_ANSWERS})
        assert response.status_code == 200
        body = response.json()
        assert body["student_id"] == "asha"
        assert body["profile"]["answered"] == 10
        assert body["profile"]["preferences"]["explanation_format"]["narrative"] == 1.0
        assert body["settings"]["response_format"] == "narrative"
        assert body["settings"]["persona_mode"] == "teacher"

    def test_partial_answers_are_accepted(self, client):
        response = client.post("/learner/asha/answers", json={"age": 12, "answers": {"4": "A"}})
        assert response.status_code == 200
        assert response.json()["profile"]["skipped"] == [1, 2, 3, 5, 6, 7, 8, 9, 10]

    def test_rejects_an_invalid_option(self, client):
        response = client.post("/learner/asha/answers", json={"age": 12, "answers": {"1": "Z"}})
        assert response.status_code == 422

    def test_rejects_an_unknown_scene(self, client):
        response = client.post("/learner/asha/answers", json={"age": 12, "answers": {"99": "A"}})
        assert response.status_code == 422

    def test_rejects_an_empty_submission(self, client):
        response = client.post("/learner/asha/answers", json={"age": 12, "answers": {}})
        assert response.status_code == 422

    def test_rejects_an_age_out_of_range(self, client):
        response = client.post("/learner/asha/answers", json={"age": 3, "answers": {"1": "A"}})
        assert response.status_code == 422


class TestReadBack:
    def test_profile_is_retrievable_after_submission(self, client):
        client.post("/learner/asha/answers", json={"age": 12, "answers": FULL_ANSWERS})
        response = client.get("/learner/asha/profile")
        assert response.status_code == 200
        assert response.json()["profile"]["age"] == 12

    def test_settings_are_retrievable_for_the_robot(self, client):
        """This is the endpoint Tot's chat and voice layers will call."""
        client.post("/learner/asha/answers", json={"age": 12, "answers": FULL_ANSWERS})
        response = client.get("/learner/asha/settings")
        assert response.status_code == 200
        body = response.json()
        assert "sarcasm_allowed" in body
        assert "hint_delay_seconds" in body
        assert len(body["prompt_directives"]) <= 3

    def test_unknown_student_is_a_404(self, client):
        assert client.get("/learner/nobody/profile").status_code == 404
        assert client.get("/learner/nobody/settings").status_code == 404


class TestErasure:
    def test_delete_removes_everything(self, client):
        client.post("/learner/asha/answers", json={"age": 12, "answers": FULL_ANSWERS})
        response = client.delete("/learner/asha")
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        assert client.get("/learner/asha/profile").status_code == 404

    def test_deleting_an_unknown_student_reports_false(self, client):
        assert client.delete("/learner/nobody").json()["deleted"] is False


class TestListing:
    def test_lists_students_with_profiles(self, client):
        client.post("/learner/asha/answers", json={"age": 12, "answers": {"1": "A"}})
        client.post("/learner/ravi/answers", json={"age": 9, "answers": {"1": "B"}})
        assert client.get("/learner/students").json()["students"] == ["asha", "ravi"]
