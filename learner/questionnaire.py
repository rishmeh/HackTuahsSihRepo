"""
learner/questionnaire.py — Loads the onboarding questionnaire from questionnaire.json.

The ten scenes are data, not code, so wording can be edited, A/B tested or
translated without a deploy. This module gives that data a typed shape, checks
it for integrity, and produces the view the student app is allowed to see.

Two views of the same scene exist on purpose:

  * The full scene, with each option's hidden scoring weights — server only.
  * The public view — text and options, nothing about what an answer reveals.
    A student who can see that option C means "low frustration tolerance"
    will answer to the label rather than the story.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

QUESTIONNAIRE_PATH = Path(__file__).resolve().parent / "questionnaire.json"


@dataclass(frozen=True)
class Option:
    key: str
    text: str
    # e.g. {"explanation_format": "narrative"} — a vote for one value of a
    # categorical dimension.
    preference_weights: dict[str, str]
    # e.g. {"help_seeking": 0.9} — a point estimate for a scalar trait.
    trait_weights: dict[str, float]
    # e.g. "low_stakes" — a hard rule the student set, never learned away.
    constraint: Optional[str] = None


@dataclass(frozen=True)
class Scene:
    id: int
    title: str
    text: str
    question: str
    measures: str
    options: list[Option]

    def option(self, key: str) -> Option:
        for option in self.options:
            if option.key == key:
                return option
        raise KeyError(f"scene {self.id} has no option {key!r}")


@dataclass(frozen=True)
class Corroboration:
    """Two scenes that measure the same thing — agreement means confidence."""

    dimension: str
    scenes: list[int]


@dataclass(frozen=True)
class Questionnaire:
    version: int
    title: str
    intro: str
    preference_dimensions: dict[str, list[str]]
    traits: list[str]
    constraints: list[str]
    corroboration: list[Corroboration]
    scenes: list[Scene]
    _by_id: dict[int, Scene] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {s.id: s for s in self.scenes})

    def scene(self, scene_id: int) -> Scene:
        try:
            return self._by_id[scene_id]
        except KeyError:
            raise KeyError(f"no scene with id {scene_id}") from None

    def public_view(self) -> dict:
        """The questionnaire as the student app receives it: no scoring data."""
        return {
            "version": self.version,
            "title": self.title,
            "intro": self.intro,
            "scenes": [
                {
                    "id": scene.id,
                    "title": scene.title,
                    "text": scene.text,
                    "question": scene.question,
                    "options": [{"key": o.key, "text": o.text} for o in scene.options],
                }
                for scene in self.scenes
            ],
        }


def _parse_option(raw: dict, preference_dims: dict[str, list[str]]) -> Option:
    weights = raw.get("weights", {})
    preferences: dict[str, str] = {}
    traits: dict[str, float] = {}
    constraint: Optional[str] = None

    for name, value in weights.items():
        if name == "constraint":
            constraint = value
        elif name in preference_dims:
            preferences[name] = value
        else:
            # Anything else is a scalar trait. Integrity tests confirm the
            # name is declared; here we only need the shape right.
            traits[name] = float(value)

    return Option(
        key=raw["key"],
        text=raw["text"],
        preference_weights=preferences,
        trait_weights=traits,
        constraint=constraint,
    )


def load_questionnaire(path: Path = QUESTIONNAIRE_PATH) -> Questionnaire:
    """Read and type the questionnaire JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    dims = data["dimensions"]
    preference_dims = dims["preferences"]

    scenes = [
        Scene(
            id=raw["id"],
            title=raw["title"],
            text=raw["text"],
            question=raw["question"],
            measures=raw.get("measures", ""),
            options=[_parse_option(o, preference_dims) for o in raw["options"]],
        )
        for raw in data["scenes"]
    ]

    return Questionnaire(
        version=data["version"],
        title=data["title"],
        intro=data.get("intro", ""),
        preference_dimensions=preference_dims,
        traits=list(dims["traits"]),
        constraints=list(dims["constraints"]),
        corroboration=[
            Corroboration(dimension=c["dimension"], scenes=list(c["scenes"]))
            for c in data.get("corroboration", [])
        ],
        scenes=scenes,
    )
