"""
tests/test_vision_face_store.py — Unit tests for the on-device face database.

The store is the privacy boundary of the whole project: it must hold face
*embeddings* and never face *images*. These tests pin that guarantee down.

Run with: pytest tests/test_vision_face_store.py -v
"""

import numpy as np
import pytest

from vision.face_store import FaceStore


@pytest.fixture
def store(tmp_path):
    """A throwaway store backed by a real SQLite file in a temp directory."""
    return FaceStore(tmp_path / "faces.db")


def _vec(seed: int, dim: int = 128) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(np.float32)


class TestEnrolment:
    def test_new_store_has_an_empty_gallery(self, store):
        assert store.load_gallery() == []

    def test_added_embedding_comes_back_in_the_gallery(self, store):
        store.add_embedding("asha", _vec(1))
        gallery = store.load_gallery()
        assert len(gallery) == 1
        assert gallery[0].student_id == "asha"
        assert len(gallery[0].embeddings) == 1

    def test_embedding_survives_the_round_trip_unchanged(self, store):
        """Float32 must come back bit-identical or match scores drift."""
        original = _vec(2)
        store.add_embedding("asha", original)
        restored = store.load_gallery()[0].embeddings[0]
        assert restored.dtype == np.float32
        np.testing.assert_array_equal(restored, original)

    def test_multiple_embeddings_group_under_one_student(self, store):
        store.add_embedding("asha", _vec(1))
        store.add_embedding("asha", _vec(2))
        store.add_embedding("asha", _vec(3))
        gallery = store.load_gallery()
        assert len(gallery) == 1
        assert len(gallery[0].embeddings) == 3

    def test_different_students_stay_separate(self, store):
        store.add_embedding("asha", _vec(1))
        store.add_embedding("ravi", _vec(2))
        gallery = store.load_gallery()
        assert {e.student_id for e in gallery} == {"asha", "ravi"}

    def test_add_embeddings_returns_how_many_were_stored(self, store):
        added = store.add_embeddings("asha", [_vec(1), _vec(2)])
        assert added == 2

    def test_data_persists_across_store_instances(self, tmp_path):
        """The Pi reboots; enrolled students must still be enrolled."""
        path = tmp_path / "faces.db"
        FaceStore(path).add_embedding("asha", _vec(1))
        assert FaceStore(path).load_gallery()[0].student_id == "asha"

    def test_rejects_an_embedding_of_the_wrong_dimension(self, store):
        with pytest.raises(ValueError):
            store.add_embedding("asha", _vec(1, dim=64))


class TestManagement:
    def test_lists_enrolled_student_ids(self, store):
        store.add_embedding("asha", _vec(1))
        store.add_embedding("ravi", _vec(2))
        assert sorted(store.list_students()) == ["asha", "ravi"]

    def test_counts_embeddings_for_one_student(self, store):
        store.add_embeddings("asha", [_vec(1), _vec(2)])
        assert store.count_embeddings("asha") == 2

    def test_deleting_a_student_removes_every_embedding(self, store):
        store.add_embeddings("asha", [_vec(1), _vec(2)])
        store.add_embedding("ravi", _vec(3))
        deleted = store.delete_student("asha")
        assert deleted == 2
        assert store.list_students() == ["ravi"]

    def test_deleting_an_unknown_student_is_harmless(self, store):
        assert store.delete_student("nobody") == 0


class TestPrivacyGuarantee:
    def test_schema_stores_no_image_data(self, store):
        """
        The deck promises 'no cloud storage of face or voice' and the plan
        says 'store embeddings, NOT images'. The schema must make storing a
        photograph impossible, not merely unlikely.
        """
        store.add_embedding("asha", _vec(1))
        columns = store.column_names()
        forbidden = {"image", "photo", "frame", "picture", "thumbnail", "jpeg", "png"}
        assert not (forbidden & {c.lower() for c in columns}), (
            f"face table must not have an image column, found: {columns}"
        )
