"""
learner/tests/test_policy.py — Tests for mapping a LearnerProfile to Tot's behaviour.

This is Phase B: the part that makes the questionnaire *do* something. The
rules under test are the precedence stack:

    1. child safety          (outside this module — safety_filter)
    2. Scene 10 constraints  the student's own rule, never learned away
    3. failure-derived gates e.g. sarcasm off for a failure-sensitive child
    4. learned values        (bandit, later)
    5. questionnaire priors
    6. defaults

Run with: pytest learner/tests/test_policy.py -v
"""

import pytest

from learner.models import LearnerProfile
from learner.policy import ENCOURAGEMENT_ARMS, MAX_PROMPT_DIRECTIVES, derive_settings


def _profile(
    *,
    age: int = 14,
    explanation_format: str = "structural",
    persona_mode: str = "teacher",
    orientation: str = "goal",
    motivation: str = "curiosity",
    skill_intro: str = "steps",
    help_seeking: float = 0.5,
    frustration_tolerance: float = 0.5,
    failure_sensitivity: float = 0.3,
    confidence_expression: float = 0.6,
    social_orientation: float = 0.5,
    constraints: list[str] | None = None,
) -> LearnerProfile:
    """A profile with one decisive value per dimension, for precise tests."""

    def one_hot(values: list[str], chosen: str) -> dict[str, float]:
        return {v: (1.0 if v == chosen else 0.0) for v in values}

    return LearnerProfile(
        questionnaire_version=1,
        age=age,
        preferences={
            "orientation": one_hot(["overview", "explore", "social", "goal"], orientation),
            "skill_intro": one_hot(["observe", "trial", "steps", "guided"], skill_intro),
            "explanation_format": one_hot(
                ["narrative", "structural", "concise", "socratic"], explanation_format
            ),
            "persona_mode": one_hot(["teacher", "peer", "socratic", "independent"], persona_mode),
            "motivation": one_hot(["curiosity", "utility", "gap", "mastery"], motivation),
        },
        traits={
            "help_seeking": help_seeking,
            "frustration_tolerance": frustration_tolerance,
            "failure_sensitivity": failure_sensitivity,
            "confidence_expression": confidence_expression,
            "social_orientation": social_orientation,
        },
        constraints=constraints or [],
        confidence={},
        answers={},
        answered=10,
        skipped=[],
    )


class TestDirectMappings:
    def test_response_format_follows_the_top_preference(self):
        assert derive_settings(_profile(explanation_format="narrative")).response_format == "narrative"

    def test_persona_mode_follows_scene_eight(self):
        assert derive_settings(_profile(persona_mode="socratic")).persona_mode == "socratic"

    def test_task_framing_follows_motivation(self):
        assert derive_settings(_profile(motivation="mastery")).task_framing == "mastery"

    def test_overview_seekers_get_the_big_picture_first(self):
        assert derive_settings(_profile(orientation="overview")).topic_intro == "overview_first"
        assert derive_settings(_profile(orientation="goal")).topic_intro == "dive_in"


class TestHints:
    """Scene 2 becomes a real, tunable number of seconds."""

    def test_high_help_seekers_get_hints_fast(self):
        assert derive_settings(_profile(help_seeking=0.9)).hint_delay_seconds == 5

    def test_moderate_help_seekers_wait_a_little(self):
        assert derive_settings(_profile(help_seeking=0.5)).hint_delay_seconds == 20

    def test_independent_learners_are_left_alone_longer(self):
        assert derive_settings(_profile(help_seeking=0.1)).hint_delay_seconds == 45

    def test_socratic_persona_hints_with_a_question(self):
        assert derive_settings(_profile(persona_mode="socratic")).hint_style == "counter_question"

    def test_high_help_seekers_just_get_the_answer(self):
        assert derive_settings(_profile(help_seeking=0.9)).hint_style == "answer"


class TestWrongAnswers:
    """Scene 6 decides how Tot reacts when the student is wrong."""

    def test_failure_sensitive_students_are_handled_gently(self):
        assert derive_settings(_profile(failure_sensitivity=0.9)).wrong_answer_style == "gentle"

    def test_error_as_information_students_get_analysis(self):
        assert derive_settings(_profile(failure_sensitivity=0.2)).wrong_answer_style == "analytical"

    def test_middle_ground_is_supportive(self):
        assert derive_settings(_profile(failure_sensitivity=0.5)).wrong_answer_style == "supportive"


class TestSarcasmGate:
    """Sarcasm must fail closed. Every path that turns it off is tested."""

    def test_allowed_for_a_confident_teen_with_no_constraints(self):
        assert derive_settings(_profile(age=15, failure_sensitivity=0.2)).sarcasm_allowed is True

    def test_off_for_failure_sensitive_students(self):
        assert derive_settings(_profile(age=15, failure_sensitivity=0.7)).sarcasm_allowed is False

    def test_off_under_eleven_regardless_of_everything_else(self):
        assert derive_settings(_profile(age=10, failure_sensitivity=0.1)).sarcasm_allowed is False

    def test_off_when_the_student_asked_for_low_stakes(self):
        settings = derive_settings(_profile(age=15, failure_sensitivity=0.1, constraints=["low_stakes"]))
        assert settings.sarcasm_allowed is False

    def test_playful_and_sarcastic_are_separate_settings(self):
        """
        Scene 10D 'make it fun' plus Scene 6A 'relieved it wasn't me': the
        student wants fun but fears failure. Playful warmth is safe; irony at
        their expense is not. Both answers must be honoured.
        """
        settings = derive_settings(_profile(age=15, failure_sensitivity=0.9, constraints=["playful"]))
        assert settings.playful is True
        assert settings.sarcasm_allowed is False


class TestConstraints:
    """Scene 10 outranks preferences and, later, learning."""

    def test_brevity_makes_responses_terse(self):
        assert derive_settings(_profile(constraints=["brevity"])).response_length == "terse"

    def test_explain_why_makes_responses_detailed(self):
        assert derive_settings(_profile(constraints=["explain_why"])).response_length == "detailed"

    def test_low_stakes_hides_scores(self):
        assert derive_settings(_profile(constraints=["low_stakes"])).show_scores is False
        assert derive_settings(_profile()).show_scores is True

    def test_brevity_turns_off_playfulness(self):
        """'Just get to the point' — jokes are the opposite of the point."""
        assert derive_settings(_profile(constraints=["brevity"])).playful is False


class TestEncouragementArms:
    """
    The arms are named and enumerable from day one so a bandit can choose
    among them later. Constraints REMOVE arms from the set rather than
    penalising them — the learner must never be able to explore into one.
    """

    def test_all_arms_are_available_by_default(self):
        assert derive_settings(_profile()).encouragement_arms == list(ENCOURAGEMENT_ARMS)

    def test_default_arm_is_chosen_from_the_available_set(self):
        settings = derive_settings(_profile())
        assert settings.encouragement_arm in settings.encouragement_arms

    def test_failure_sensitive_students_default_to_warm(self):
        assert derive_settings(_profile(failure_sensitivity=0.8)).encouragement_arm == "warm"

    def test_mastery_seekers_who_tolerate_frustration_get_challenged(self):
        settings = derive_settings(_profile(motivation="mastery", frustration_tolerance=0.8))
        assert settings.encouragement_arm == "challenge"

    def test_low_stakes_removes_the_challenge_arm_entirely(self):
        settings = derive_settings(_profile(motivation="mastery", frustration_tolerance=0.8, constraints=["low_stakes"]))
        assert "challenge" not in settings.encouragement_arms
        assert settings.encouragement_arm != "challenge"

    def test_playful_constraint_picks_the_playful_arm(self):
        assert derive_settings(_profile(constraints=["playful"])).encouragement_arm == "playful"


class TestLearnedOverrides:
    """Hook for the bandit: learned values beat priors, constraints beat learned."""

    def test_a_learned_arm_overrides_the_questionnaire_default(self):
        settings = derive_settings(_profile(), learned={"encouragement_arm": "plain"})
        assert settings.encouragement_arm == "plain"

    def test_a_learned_arm_forbidden_by_a_constraint_is_refused(self):
        """Even a bandit that somehow proposes 'challenge' cannot get past low_stakes."""
        settings = derive_settings(
            _profile(constraints=["low_stakes"]), learned={"encouragement_arm": "challenge"}
        )
        assert settings.encouragement_arm != "challenge"

    def test_a_learned_format_overrides_the_prior(self):
        settings = derive_settings(_profile(explanation_format="structural"), learned={"response_format": "narrative"})
        assert settings.response_format == "narrative"


class TestPromptDirectives:
    """A 0.6B model cannot follow eleven style instructions. Three, at most."""

    def test_never_more_than_the_cap(self):
        for constraints in ([], ["brevity"], ["low_stakes"], ["playful"]):
            settings = derive_settings(_profile(constraints=constraints))
            assert len(settings.prompt_directives) <= MAX_PROMPT_DIRECTIVES

    def test_directives_mention_the_chosen_format(self):
        settings = derive_settings(_profile(explanation_format="narrative"))
        assert any("story" in d.lower() or "narrative" in d.lower() for d in settings.prompt_directives)


class TestExplainability:
    def test_every_setting_comes_with_a_reason(self):
        """The parent dashboard, and a judge, should be able to see why."""
        settings = derive_settings(_profile(constraints=["low_stakes"], failure_sensitivity=0.9))
        joined = " ".join(settings.reasons).lower()
        assert "sarcasm" in joined
        assert "low_stakes" in joined or "relaxed" in joined


class TestDefaultSettings:
    """
    A student who has not done the questionnaire yet still needs a persona.
    Defaults must be the safe middle: no sarcasm, warm, normal length.
    """

    def test_default_settings_exist_without_a_questionnaire(self):
        from learner.policy import default_settings

        settings = default_settings(age=10)
        assert settings.response_format in ("narrative", "structural", "concise", "socratic")
        assert settings.encouragement_arm == "warm"
        assert settings.response_length == "normal"

    def test_defaults_never_allow_sarcasm(self):
        """Nothing is known about this child yet. Fail closed."""
        from learner.policy import default_settings

        for age in (6, 10, 14, 17):
            assert default_settings(age=age).sarcasm_allowed is False, age

    def test_defaults_carry_prompt_directives(self):
        from learner.policy import default_settings

        assert 1 <= len(default_settings(age=10).prompt_directives) <= MAX_PROMPT_DIRECTIVES
