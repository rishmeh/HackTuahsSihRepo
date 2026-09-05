"""
learner/tests/test_profile_store.py — Tests for persisting learner profiles.

Run with: pytest learner/tests/test_profile_store.py -v
"""

import pytest

from learner.models import LearnerProfile
from learner.profile_store import ProfileStore


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "learner.db")


def _profile(age: int = 12, fmt: str = "narrative") -> LearnerProfile:
    return LearnerProfile(
        questionnaire_version=1,
        age=age,
        preferences={"explanation_format": {"narrative": 1.0 if fmt == "narrative" else 0.0,
                                            "structural": 0.0 if fmt == "narrative" else 1.0,
                                            "concise": 0.0, "socratic": 0.0}},
        traits={"help_seeking": 0.5},
        constraints=["low_stakes"],
        confidence={"explanation_format": 0.7},
        answers={4: "A"},
        answered=1,
        skipped=[1, 2, 3, 5, 6, 7, 8, 9, 10],
    )


class TestRoundTrip:
    def test_missing_student_returns_none(self, store):
        assert store.get("nobody") is None

    def test_saved_profile_comes_back_equal(self, store):
        original = _profile()
        store.save("asha", original)
        stored = store.get("asha")
        assert stored is not None
        assert stored.profile == original

    def test_integer_scene_keys_survive_json(self, store):
        """JSON turns dict keys into strings; they must come back as ints."""
        store.save("asha", _profile())
        assert store.get("asha").profile.answers == {4: "A"}

    def test_saving_again_replaces_the_profile(self, store):
        store.save("asha", _profile(fmt="narrative"))
        store.save("asha", _profile(fmt="structural"))
        assert store.get("asha").profile.top("explanation_format") == "structural"

    def test_records_when_it_was_updated(self, store):
        store.save("asha", _profile())
        assert store.get("asha").updated_at is not None

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "learner.db"
        ProfileStore(path).save("asha", _profile())
        assert ProfileStore(path).get("asha") is not None


class TestManagement:
    def test_lists_students_with_profiles(self, store):
        store.save("asha", _profile())
        store.save("ravi", _profile())
        assert store.list_students() == ["asha", "ravi"]

    def test_delete_removes_the_profile(self, store):
        store.save("asha", _profile())
        assert store.delete("asha") is True
        assert store.get("asha") is None

    def test_deleting_an_unknown_student_is_harmless(self, store):
        assert store.delete("nobody") is False
