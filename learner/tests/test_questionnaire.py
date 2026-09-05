"""
learner/tests/test_questionnaire.py — Tests for loading and exposing the questionnaire.

The scenes live in questionnaire.json so wording can be edited or translated
without touching code. These tests keep that data honest: every option must
point at a declared dimension, and the view sent to the app must never leak
the scoring weights.

Run with: pytest learner/tests/test_questionnaire.py -v
"""

import pytest

from learner.questionnaire import Questionnaire, load_questionnaire


@pytest.fixture(scope="module")
def q() -> Questionnaire:
    return load_questionnaire()


class TestShape:
    def test_has_ten_scenes_numbered_in_order(self, q):
        assert [s.id for s in q.scenes] == list(range(1, 11))

    def test_every_scene_has_four_options_keyed_a_to_d(self, q):
        for scene in q.scenes:
            assert [o.key for o in scene.options] == ["A", "B", "C", "D"], scene.id

    def test_scene_lookup_by_id(self, q):
        assert q.scene(4).title == "The Storyteller"

    def test_unknown_scene_id_raises(self, q):
        with pytest.raises(KeyError):
            q.scene(11)


class TestDataIntegrity:
    """A typo in the JSON must fail here, not silently score as nothing."""

    def test_every_preference_weight_names_a_declared_dimension_and_value(self, q):
        for scene in q.scenes:
            for option in scene.options:
                for dim, value in option.preference_weights.items():
                    assert dim in q.preference_dimensions, f"scene {scene.id}{option.key}: {dim}"
                    assert value in q.preference_dimensions[dim], (
                        f"scene {scene.id}{option.key}: {dim}={value}"
                    )

    def test_every_trait_weight_is_a_declared_trait_in_range(self, q):
        for scene in q.scenes:
            for option in scene.options:
                for trait, value in option.trait_weights.items():
                    assert trait in q.traits, f"scene {scene.id}{option.key}: {trait}"
                    assert 0.0 <= value <= 1.0, f"scene {scene.id}{option.key}: {trait}={value}"

    def test_every_constraint_is_declared(self, q):
        for scene in q.scenes:
            for option in scene.options:
                if option.constraint is not None:
                    assert option.constraint in q.constraints

    def test_every_option_scores_something(self, q):
        """An option with no weights would be a question that measures nothing."""
        for scene in q.scenes:
            for option in scene.options:
                assert (
                    option.preference_weights or option.trait_weights or option.constraint
                ), f"scene {scene.id}{option.key} has no weights"

    def test_corroboration_pairs_reference_real_scenes_and_dimensions(self, q):
        for pair in q.corroboration:
            assert len(pair.scenes) == 2
            for scene_id in pair.scenes:
                q.scene(scene_id)
            assert pair.dimension in q.preference_dimensions or pair.dimension in q.traits

    def test_every_preference_dimension_is_measured_by_at_least_one_scene(self, q):
        measured = {
            dim
            for scene in q.scenes
            for option in scene.options
            for dim in option.preference_weights
        }
        assert measured == set(q.preference_dimensions)


class TestPublicView:
    """What the student app receives."""

    def test_public_view_contains_scene_text_and_options(self, q):
        view = q.public_view()
        assert view["title"] == "The Mysterious World"
        assert len(view["scenes"]) == 10
        first = view["scenes"][0]
        assert first["id"] == 1
        assert first["question"] == "Where do you want to go first?"
        assert [o["key"] for o in first["options"]] == ["A", "B", "C", "D"]
        assert "tower" in first["options"][0]["text"]

    def test_public_view_never_leaks_scoring(self, q):
        """
        Weights and 'measures' notes describe what each answer reveals. Sending
        them to the client would let a student game the quiz, and reads as
        labelling a child. They stay server-side.
        """
        import json

        serialised = json.dumps(q.public_view())
        for forbidden in ("weights", "measures", "failure_sensitivity", "help_seeking"):
            assert forbidden not in serialised, forbidden

    def test_public_view_carries_the_version_so_answers_can_be_rescored_later(self, q):
        assert q.public_view()["version"] == q.version
