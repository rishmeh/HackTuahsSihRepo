"""
learner/models.py — Data models for the learner package.

The LearnerProfile is the output of the onboarding questionnaire and the input
to everything downstream: the behaviour mapping (policy.py) now, the bandit
priors later.

One rule shapes its whole design: **weights, never labels.** A profile does not
say "visual learner"; it says narrative 0.6, structural 0.2, concise 0.1,
socratic 0.1 — with a confidence attached. A label is a verdict about a child.
A weight is a hypothesis that later evidence is allowed to move.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LearnerProfile(BaseModel):
    """
    What the questionnaire tells us about how one student prefers to learn.

    Attributes:
        preferences: For each categorical dimension, a distribution over its
            values that sums to 1.0.
        traits: Scalar 0–1 estimates, e.g. help_seeking, failure_sensitivity.
        constraints: Hard rules the student set (Scene 10). These sit outside
            anything learnable — they are never overridden by evidence.
        confidence: Per dimension, how much to trust the estimate, 0–1. Paired
            scenes that agree score high; disagreement or a single source score
            lower; younger children are scaled down. This becomes prior strength
            when the bandit is added.
        answers: The raw answers, kept so the profile can be rescored if the
            scoring rules change without asking the student again.
    """

    questionnaire_version: int
    age: int = Field(..., ge=4, le=18)
    preferences: dict[str, dict[str, float]]
    traits: dict[str, float]
    constraints: list[str]
    confidence: dict[str, float]
    answers: dict[int, str]
    answered: int
    skipped: list[int]
    scored_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def top(self, dimension: str) -> str:
        """The most likely value of a preference dimension."""
        distribution = self.preferences[dimension]
        return max(distribution, key=distribution.get)

    def has_constraint(self, name: str) -> bool:
        return name in self.constraints


class AnswerSubmission(BaseModel):
    """What the student app posts when the questionnaire is finished."""

    age: int = Field(..., ge=4, le=18, description="Student age in years")
    answers: dict[int, str] = Field(
        ...,
        description="Scene id → option key, e.g. {1: 'A', 2: 'C'}. Skipped scenes are omitted.",
    )

    @field_validator("answers")
    @classmethod
    def _at_least_one_answer(cls, value: dict[int, str]) -> dict[int, str]:
        if not value:
            raise ValueError("at least one answer is required")
        return value


class ProfileResponse(BaseModel):
    """A stored profile, as returned by the API."""

    student_id: str
    profile: LearnerProfile
    updated_at: Optional[str] = None


class TotSettings(BaseModel):
    """
    What Tot should actually do for this student — the output of policy.py.

    Everything here is either read by code (hint timing, phrase pools, persona
    framing) or, for at most three fields, turned into prompt directives for
    the SLM. A 0.6B model cannot follow eleven style instructions at once, so
    the prompt gets only what code cannot do.

    ``encouragement_arms`` is the set a bandit may choose from later. It is
    already filtered by the student's constraints — a forbidden arm is absent,
    not merely discouraged, so the learner can never explore into it.
    """

    response_format: str
    response_length: str
    hint_delay_seconds: int
    hint_style: str
    wrong_answer_style: str
    sarcasm_allowed: bool
    playful: bool
    encouragement_arm: str
    encouragement_arms: list[str]
    persona_mode: str
    topic_intro: str
    task_framing: str
    answer_invite: str
    show_scores: bool
    prompt_directives: list[str] = Field(
        ..., description="At most three style instructions for the SLM system prompt"
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable explanation of each non-default choice",
    )
