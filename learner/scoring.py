"""
learner/scoring.py — Turns questionnaire answers into a LearnerProfile.

Pure function: answers in, profile out. No I/O, no clock, no model — which is
why every rule below has a fast unit test.

How an answer becomes a number:

  Preferences   Each option casts a vote for one value of a categorical
                dimension. Votes are normalised into a distribution. Two
                scenes voting narrative → narrative 1.0. One narrative, one
                concise → 0.5 each. No votes → uniform.

  Traits        Each option gives a point estimate (0–1). Several scenes may
                speak to one trait; the profile holds their mean.

  Constraints   Scene 10 answers are collected as-is. They are rules, not
                weights.

  Confidence    How much to trust each dimension, 0–1:
                  two sources that agree      CONFIDENCE_AGREE
                  a single source             CONFIDENCE_SINGLE
                  two sources that disagree   CONFIDENCE_DISAGREE
                  no source                   0.0
                then scaled down for younger children, whose self-reports
                are noisier. The preference itself is never scaled — only
                how firmly we hold it.

The disagreement case is deliberate. A child who picks "story" in one scene
and "just the facts" in another has not given bad data — they have told us
they have no stable preference here, so the bandit should explore freely.
"""

from __future__ import annotations

from collections import defaultdict

from learner.models import LearnerProfile
from learner.questionnaire import Questionnaire

# Confidence assigned by how many scenes spoke to a dimension and whether they agreed.
CONFIDENCE_AGREE = 1.0
CONFIDENCE_SINGLE = 0.7
CONFIDENCE_DISAGREE = 0.5

# Two trait estimates within this distance count as agreeing.
TRAIT_AGREEMENT_TOLERANCE = 0.3

# Younger children answer more aspirationally and less consistently, so their
# answers are held more loosely and behaviour is allowed to override sooner.
AGE_FACTOR_YOUNG = 0.6   # under 9
AGE_FACTOR_MIDDLE = 0.8  # 9–12
AGE_FACTOR_TEEN = 1.0    # 13+

TRAIT_DEFAULT = 0.5


def age_factor(age: int) -> float:
    if age < 9:
        return AGE_FACTOR_YOUNG
    if age <= 12:
        return AGE_FACTOR_MIDDLE
    return AGE_FACTOR_TEEN


def _normalise_answers(answers: dict[int, str], q: Questionnaire) -> dict[int, str]:
    """Validate scene ids and option keys; upper-case the keys."""
    clean: dict[int, str] = {}
    for scene_id, key in answers.items():
        scene_id = int(scene_id)
        try:
            scene = q.scene(scene_id)
        except KeyError:
            raise ValueError(f"unknown scene id {scene_id}") from None
        key = str(key).strip().upper()
        try:
            scene.option(key)
        except KeyError:
            raise ValueError(f"scene {scene_id} has no option {key!r}") from None
        clean[scene_id] = key
    return clean


def _confidence_from_sources(sources: list, agree) -> float:
    """Confidence given the contributing sources and an agreement predicate."""
    if not sources:
        return 0.0
    if len(sources) == 1:
        return CONFIDENCE_SINGLE
    return CONFIDENCE_AGREE if agree(sources) else CONFIDENCE_DISAGREE


def score_answers(
    answers: dict[int, str], age: int, questionnaire: Questionnaire
) -> LearnerProfile:
    """
    Score a set of answers into a LearnerProfile.

    Args:
        answers: Scene id → option key. Skipped scenes are simply absent.
        age: Student age, used only to scale confidence.
        questionnaire: The loaded questionnaire the answers refer to.

    Raises:
        ValueError: On an unknown scene id or option key.
    """
    q = questionnaire
    answers = _normalise_answers(answers, q)

    votes: dict[str, list[str]] = defaultdict(list)
    trait_estimates: dict[str, list[float]] = defaultdict(list)
    constraints: list[str] = []

    for scene_id, key in answers.items():
        option = q.scene(scene_id).option(key)
        for dim, value in option.preference_weights.items():
            votes[dim].append(value)
        for trait, value in option.trait_weights.items():
            trait_estimates[trait].append(value)
        if option.constraint is not None and option.constraint not in constraints:
            constraints.append(option.constraint)

    # -- preferences: votes → distribution ----------------------------------
    preferences: dict[str, dict[str, float]] = {}
    for dim, values in q.preference_dimensions.items():
        cast = votes.get(dim, [])
        if cast:
            preferences[dim] = {v: cast.count(v) / len(cast) for v in values}
        else:
            preferences[dim] = {v: 1.0 / len(values) for v in values}

    # -- traits: estimates → mean --------------------------------------------
    traits: dict[str, float] = {}
    for trait in q.traits:
        estimates = trait_estimates.get(trait, [])
        traits[trait] = sum(estimates) / len(estimates) if estimates else TRAIT_DEFAULT

    # -- confidence ----------------------------------------------------------
    factor = age_factor(age)
    confidence: dict[str, float] = {}

    for dim in q.preference_dimensions:
        cast = votes.get(dim, [])
        raw = _confidence_from_sources(cast, agree=lambda c: len(set(c)) == 1)
        confidence[dim] = raw * factor

    for trait in q.traits:
        estimates = trait_estimates.get(trait, [])
        raw = _confidence_from_sources(
            estimates,
            agree=lambda e: (max(e) - min(e)) <= TRAIT_AGREEMENT_TOLERANCE,
        )
        confidence[trait] = raw * factor

    all_ids = [s.id for s in q.scenes]
    return LearnerProfile(
        questionnaire_version=q.version,
        age=age,
        preferences=preferences,
        traits=traits,
        constraints=constraints,
        confidence=confidence,
        answers=answers,
        answered=len(answers),
        skipped=[i for i in all_ids if i not in answers],
    )
