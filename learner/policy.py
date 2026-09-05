"""
learner/policy.py — Turns a LearnerProfile into what Tot actually does.

This is the step that makes the questionnaire matter. A profile is a set of
weights; TotSettings is a set of decisions: how long to wait before hinting,
how to react to a wrong answer, whether a joke is ever allowed.

Decisions are resolved in a fixed precedence order, and the order is the
design:

    1. child safety          handled upstream by chat/safety_filter — absolute
    2. Scene 10 constraints  the rule the student set; never learned away
    3. failure-derived gates sarcasm off for a failure-sensitive child
    4. learned values        supplied by the bandit, later
    5. questionnaire priors
    6. defaults

Two things people conflate are kept apart on purpose:

  * playful   — warmth, silly framing, enthusiasm. Always safe.
  * sarcasm   — irony at someone's expense. Gated hard, fails closed.

A student who says "make it fun" and also "I dread being wrong" gets the
first and not the second.

The encouragement *arms* are named here so a bandit can choose among them
later without any restructuring. Constraints remove arms from the set rather
than penalising them: a forbidden action must be unreachable, not unlikely.
"""

from __future__ import annotations

from typing import Optional

from learner import config
from learner.models import LearnerProfile, TotSettings

# The choices a future bandit may learn among. Order is the default preference.
ENCOURAGEMENT_ARMS: tuple[str, ...] = ("warm", "playful", "challenge", "plain")

# Arms that a given constraint makes unsafe or contradictory.
_ARMS_FORBIDDEN_BY_CONSTRAINT: dict[str, set[str]] = {
    "low_stakes": {"challenge"},   # "keep it relaxed" — no daring them
    "brevity": {"playful"},        # "get to the point" — no banter
}

MAX_PROMPT_DIRECTIVES = 3

# Trait thresholds. Kept as named numbers so they can be tuned in one place.
HELP_SEEKING_HIGH = 0.7
HELP_SEEKING_LOW = 0.4
FAILURE_SENSITIVE = 0.7
FAILURE_ROBUST = 0.3
SARCASM_FAILURE_CUTOFF = 0.6
CHALLENGE_TOLERANCE = 0.6
CONFIDENCE_PRIVATE = 0.4

_FORMAT_DIRECTIVES = {
    "narrative": "Explain through a short story or a concrete scenario with characters.",
    "structural": "Explain with clear structure: name the parts, then how they connect.",
    "concise": "Give the key facts as a short list. No preamble.",
    "socratic": "Answer briefly, then ask one question that helps the student think further.",
}
_LENGTH_DIRECTIVES = {
    "terse": "Keep it to two or three sentences.",
    "normal": "Keep it to one short paragraph.",
    "detailed": "Always explain the why, not just the what.",
}
_WRONG_ANSWER_DIRECTIVES = {
    "gentle": "If the student is wrong, normalise it warmly before correcting; never dwell on the mistake.",
    "supportive": "If the student is wrong, acknowledge the effort, then correct clearly.",
    "analytical": "If the student is wrong, treat it as interesting: explore why that answer was tempting.",
}


def derive_settings(
    profile: LearnerProfile, learned: Optional[dict[str, str]] = None
) -> TotSettings:
    """
    Resolve a profile (and any learned overrides) into concrete behaviour.

    Args:
        profile: The scored questionnaire.
        learned: Values a bandit has learned for this student, e.g.
            {"encouragement_arm": "plain"}. They override questionnaire
            priors but never constraints.
    """
    learned = learned or {}
    reasons: list[str] = []
    traits = profile.traits
    has = profile.has_constraint

    # -- constraints first: they bound everything below --------------------
    forbidden_arms: set[str] = set()
    for constraint in profile.constraints:
        forbidden_arms |= _ARMS_FORBIDDEN_BY_CONSTRAINT.get(constraint, set())
    arms = [a for a in ENCOURAGEMENT_ARMS if a not in forbidden_arms]
    if forbidden_arms:
        reasons.append(
            f"constraints {profile.constraints} remove encouragement arms {sorted(forbidden_arms)}"
        )

    # -- response shape ------------------------------------------------------
    response_format = learned.get("response_format") or profile.top("explanation_format")
    if "response_format" in learned:
        reasons.append(f"response_format={response_format!r} learned from behaviour")

    if has("brevity"):
        response_length = "terse"
        reasons.append("response_length=terse: student asked Tot not to talk too much")
    elif has("explain_why"):
        response_length = "detailed"
        reasons.append("response_length=detailed: student asked to always understand why")
    else:
        response_length = "normal"

    # -- hints ---------------------------------------------------------------
    help_seeking = traits.get("help_seeking", 0.5)
    if help_seeking >= HELP_SEEKING_HIGH:
        hint_delay, hint_style = 5, "answer"
    elif help_seeking >= HELP_SEEKING_LOW:
        hint_delay, hint_style = 20, "nudge"
    else:
        hint_delay, hint_style = 45, "nudge"
        reasons.append("hint_delay=45s: student prefers to work it out alone")

    persona_mode = profile.top("persona_mode")
    if persona_mode == "socratic":
        hint_style = "counter_question"

    # -- wrong answers and the sarcasm gate ----------------------------------
    failure_sensitivity = traits.get("failure_sensitivity", 0.5)
    if failure_sensitivity >= FAILURE_SENSITIVE:
        wrong_answer_style = "gentle"
        reasons.append("wrong_answer_style=gentle: student is sensitive to being wrong")
    elif failure_sensitivity <= FAILURE_ROBUST:
        wrong_answer_style = "analytical"
    else:
        wrong_answer_style = "supportive"

    sarcasm_allowed = True
    if profile.age < config.SARCASM_MIN_AGE:
        sarcasm_allowed = False
        reasons.append(f"sarcasm off: under {config.SARCASM_MIN_AGE}")
    if failure_sensitivity >= SARCASM_FAILURE_CUTOFF:
        sarcasm_allowed = False
        reasons.append("sarcasm off: student is sensitive to failure")
    if has("low_stakes"):
        sarcasm_allowed = False
        reasons.append("sarcasm off: student asked for a relaxed, low_stakes tone")

    # Playfulness is separate from sarcasm and is only switched off by a
    # student who explicitly wants efficiency.
    playful = not has("brevity")

    # -- encouragement arm ---------------------------------------------------
    if has("playful"):
        default_arm = "playful"
    elif failure_sensitivity >= SARCASM_FAILURE_CUTOFF:
        default_arm = "warm"
    elif (
        profile.top("motivation") == "mastery"
        and traits.get("frustration_tolerance", 0.5) >= CHALLENGE_TOLERANCE
    ):
        default_arm = "challenge"
    elif profile.top("motivation") == "utility":
        default_arm = "plain"
    else:
        default_arm = "warm"

    arm = learned.get("encouragement_arm", default_arm)
    if arm not in arms:
        # Either the default or a learned value collided with a constraint.
        # Constraints win; fall back to the first permitted arm.
        if arm == learned.get("encouragement_arm"):
            reasons.append(f"learned arm {arm!r} refused: forbidden by constraints")
        arm = arms[0]
    elif "encouragement_arm" in learned:
        reasons.append(f"encouragement_arm={arm!r} learned from behaviour")

    # -- framing -------------------------------------------------------------
    topic_intro = "overview_first" if profile.top("orientation") == "overview" else "dive_in"
    task_framing = profile.top("motivation")
    answer_invite = (
        "private" if traits.get("confidence_expression", 0.5) < CONFIDENCE_PRIVATE else "aloud"
    )
    show_scores = not has("low_stakes")
    if not show_scores:
        reasons.append("show_scores=False: low_stakes")

    # -- the few things only the model can do --------------------------------
    prompt_directives = [
        _FORMAT_DIRECTIVES[response_format],
        _LENGTH_DIRECTIVES[response_length],
        _WRONG_ANSWER_DIRECTIVES[wrong_answer_style],
    ][:MAX_PROMPT_DIRECTIVES]

    return TotSettings(
        response_format=response_format,
        response_length=response_length,
        hint_delay_seconds=hint_delay,
        hint_style=hint_style,
        wrong_answer_style=wrong_answer_style,
        sarcasm_allowed=sarcasm_allowed,
        playful=playful,
        encouragement_arm=arm,
        encouragement_arms=arms,
        persona_mode=persona_mode,
        topic_intro=topic_intro,
        task_framing=task_framing,
        answer_invite=answer_invite,
        show_scores=show_scores,
        prompt_directives=prompt_directives,
        reasons=reasons,
    )


def default_settings(age: int = 10) -> TotSettings:
    """
    Settings for a student who has not done the questionnaire yet.

    Built from a neutral profile — uniform preferences, midpoint traits, no
    constraints — and then made deliberately cautious: sarcasm is off because
    nothing is known about this child yet. The persona must fail closed.
    """
    neutral = LearnerProfile(
        questionnaire_version=0,
        age=age,
        preferences={
            "orientation": {v: 0.25 for v in ("overview", "explore", "social", "goal")},
            "skill_intro": {v: 0.25 for v in ("observe", "trial", "steps", "guided")},
            "explanation_format": {v: 0.25 for v in ("narrative", "structural", "concise", "socratic")},
            "persona_mode": {v: 0.25 for v in ("teacher", "peer", "socratic", "independent")},
            "motivation": {v: 0.25 for v in ("curiosity", "utility", "gap", "mastery")},
        },
        traits={t: 0.5 for t in ("help_seeking", "frustration_tolerance", "failure_sensitivity",
                                 "confidence_expression", "social_orientation")},
        constraints=[],
        confidence={},
        answers={},
        answered=0,
        skipped=list(range(1, 11)),
    )
    settings = derive_settings(neutral)
    return settings.model_copy(update={
        "sarcasm_allowed": False,
        "reasons": settings.reasons + ["sarcasm off: no questionnaire yet, nothing known about this student"],
    })
