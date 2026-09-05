"""
learner/tests/test_scoring.py — Tests for turning answers into a LearnerProfile.

The rules under test:

  * Preferences are distributions, never single labels.
  * Traits average across every scene that speaks to them.
  * Paired scenes that agree raise confidence; disagreement lowers it.
  * Younger children's self-reports are held more loosely.
  * A skipped scene yields uniform ignorance, never a guess.

Run with: pytest learner/tests/test_scoring.py -v
"""

import pytest

from learner.questionnaire import load_questionnaire
from learner.scoring import (
    AGE_FACTOR_TEEN,
    AGE_FACTOR_YOUNG,
    CONFIDENCE_AGREE,
    CONFIDENCE_DISAGREE,
    CONFIDENCE_SINGLE,
    score_answers,
)


@pytest.fixture(scope="module")
def q():
    return load_questionnaire()


def _all(letter: str) -> dict[int, str]:
    return {i: letter for i in range(1, 11)}


class TestPreferences:
    def test_preferences_are_distributions_that_sum_to_one(self, q):
        profile = score_answers(_all("A"), age=14, questionnaire=q)
        for dim, dist in profile.preferences.items():
            assert sum(dist.values()) == pytest.approx(1.0), dim
            assert set(dist) == set(q.preference_dimensions[dim]), dim

    def test_two_agreeing_scenes_give_a_decisive_preference(self, q):
        """4A (story) and 7B (traveller tales) both vote narrative."""
        profile = score_answers({4: "A", 7: "B"}, age=14, questionnaire=q)
        assert profile.preferences["explanation_format"]["narrative"] == pytest.approx(1.0)

    def test_two_disagreeing_scenes_split_the_preference(self, q):
        """4C (just facts) vs 7B (stories): no stable preference."""
        profile = score_answers({4: "C", 7: "B"}, age=14, questionnaire=q)
        fmt = profile.preferences["explanation_format"]
        assert fmt["concise"] == pytest.approx(0.5)
        assert fmt["narrative"] == pytest.approx(0.5)

    def test_top_preference_helper_returns_the_argmax(self, q):
        profile = score_answers({8: "C"}, age=14, questionnaire=q)
        assert profile.top("persona_mode") == "socratic"

    def test_unanswered_dimension_is_uniform(self, q):
        profile = score_answers({}, age=14, questionnaire=q)
        dist = profile.preferences["motivation"]
        assert all(v == pytest.approx(0.25) for v in dist.values())


class TestTraits:
    def test_single_scene_trait_is_taken_as_given(self, q):
        profile = score_answers({6: "A"}, age=14, questionnaire=q)
        assert profile.traits["failure_sensitivity"] == pytest.approx(0.9)

    def test_traits_average_across_contributing_scenes(self, q):
        """
        help_seeking is spoken to by 2C (0.9), 3B (0.15) and 8D (0.1).
        The profile should hold their mean, not the last one seen.
        """
        profile = score_answers({2: "C", 3: "B", 8: "D"}, age=14, questionnaire=q)
        assert profile.traits["help_seeking"] == pytest.approx((0.9 + 0.15 + 0.1) / 3)

    def test_unmeasured_trait_defaults_to_the_midpoint(self, q):
        profile = score_answers({}, age=14, questionnaire=q)
        assert profile.traits["frustration_tolerance"] == pytest.approx(0.5)

    def test_a_and_d_on_the_riddle_stone_differ_on_tolerance_not_help_seeking(self, q):
        """Both avoid help; only one of them enjoys being stuck. Two numbers, not one."""
        a = score_answers({2: "A"}, age=14, questionnaire=q).traits
        d = score_answers({2: "D"}, age=14, questionnaire=q).traits
        assert abs(a["help_seeking"] - d["help_seeking"]) < 0.15
        assert d["frustration_tolerance"] > a["frustration_tolerance"]


class TestConstraints:
    def test_scene_ten_sets_a_hard_constraint(self, q):
        profile = score_answers({10: "C"}, age=14, questionnaire=q)
        assert profile.constraints == ["low_stakes"]

    def test_no_scene_ten_means_no_constraints(self, q):
        profile = score_answers({1: "A"}, age=14, questionnaire=q)
        assert profile.constraints == []


class TestConfidence:
    """Confidence later becomes prior strength for the bandit."""

    def test_agreeing_pair_is_fully_confident(self, q):
        profile = score_answers({4: "A", 7: "B"}, age=14, questionnaire=q)
        assert profile.confidence["explanation_format"] == pytest.approx(CONFIDENCE_AGREE)

    def test_disagreeing_pair_is_less_confident(self, q):
        profile = score_answers({4: "C", 7: "B"}, age=14, questionnaire=q)
        assert profile.confidence["explanation_format"] == pytest.approx(CONFIDENCE_DISAGREE)
        assert CONFIDENCE_DISAGREE < CONFIDENCE_SINGLE < CONFIDENCE_AGREE

    def test_one_scene_of_a_pair_is_moderately_confident(self, q):
        profile = score_answers({4: "A"}, age=14, questionnaire=q)
        assert profile.confidence["explanation_format"] == pytest.approx(CONFIDENCE_SINGLE)

    def test_unanswered_dimension_has_zero_confidence(self, q):
        profile = score_answers({}, age=14, questionnaire=q)
        assert profile.confidence["explanation_format"] == 0.0
        assert profile.confidence["help_seeking"] == 0.0

    def test_trait_contributors_that_agree_are_confident(self, q):
        """5D (0.7) and 6A (0.9) on failure sensitivity are within tolerance."""
        profile = score_answers({5: "D", 6: "A"}, age=14, questionnaire=q)
        assert profile.confidence["failure_sensitivity"] == pytest.approx(CONFIDENCE_AGREE)

    def test_trait_contributors_that_clash_are_not(self, q):
        """5A (0.1, shouts answers) with 6A (0.9, dreads being wrong) contradict."""
        profile = score_answers({5: "A", 6: "A"}, age=14, questionnaire=q)
        assert profile.confidence["failure_sensitivity"] == pytest.approx(CONFIDENCE_DISAGREE)


class TestAgeScaling:
    def test_young_children_are_held_more_loosely(self, q):
        teen = score_answers({4: "A", 7: "B"}, age=15, questionnaire=q)
        young = score_answers({4: "A", 7: "B"}, age=7, questionnaire=q)
        assert young.confidence["explanation_format"] == pytest.approx(
            teen.confidence["explanation_format"] * AGE_FACTOR_YOUNG / AGE_FACTOR_TEEN
        )
        assert young.confidence["explanation_format"] < teen.confidence["explanation_format"]

    def test_age_does_not_change_the_preference_itself(self, q):
        """Scaling affects how much we trust the answer, not what it was."""
        teen = score_answers({4: "A", 7: "B"}, age=15, questionnaire=q)
        young = score_answers({4: "A", 7: "B"}, age=7, questionnaire=q)
        assert teen.preferences == young.preferences


class TestBookkeeping:
    def test_records_what_was_answered_and_skipped(self, q):
        profile = score_answers({1: "A", 4: "B"}, age=12, questionnaire=q)
        assert profile.answered == 2
        assert profile.skipped == [2, 3, 5, 6, 7, 8, 9, 10]

    def test_carries_questionnaire_version_and_age(self, q):
        profile = score_answers({1: "A"}, age=12, questionnaire=q)
        assert profile.questionnaire_version == q.version
        assert profile.age == 12

    def test_raw_answers_are_kept_so_the_profile_can_be_rescored(self, q):
        profile = score_answers({1: "A", 4: "B"}, age=12, questionnaire=q)
        assert profile.answers == {1: "A", 4: "B"}


class TestValidation:
    def test_rejects_an_unknown_option_key(self, q):
        with pytest.raises(ValueError, match="option"):
            score_answers({1: "E"}, age=12, questionnaire=q)

    def test_rejects_an_unknown_scene_id(self, q):
        with pytest.raises(ValueError, match="scene"):
            score_answers({42: "A"}, age=12, questionnaire=q)

    def test_option_keys_are_case_insensitive(self, q):
        lower = score_answers({4: "a"}, age=12, questionnaire=q)
        upper = score_answers({4: "A"}, age=12, questionnaire=q)
        assert lower.preferences == upper.preferences
