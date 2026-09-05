"""
persona/voice.py — How Tot sounds, derived from the same settings as how it talks.

Piper exposes three synthesis knobs:

    length_scale   pace — 1.0 natural, lower faster, higher slower
    noise_scale    expressiveness / variation in the voice
    noise_w        variation in phoneme timing

Persona shows up in delivery as much as in words. A playful student gets a
quicker read; a failure-sensitive one is never corrected briskly; a student
who asked Tot to get to the point gets it a little faster.

All adjustments are small and clamped, because a voice that is too fast or too
slow stops being a personality and becomes hard to understand.
"""

from __future__ import annotations

from dataclasses import dataclass

from learner.models import TotSettings
from persona import config

DEFAULT_VOICE_MODEL = config.PIPER_VOICE_MODEL

# Pace adjustments, added to a base of 1.0. Negative is faster.
_ARM_PACE = {"warm": 0.0, "playful": -0.08, "challenge": -0.03, "plain": -0.02}
_WRONG_ANSWER_PACE = {"gentle": +0.08, "supportive": +0.02, "analytical": -0.02}
_LENGTH_PACE = {"terse": -0.05, "normal": 0.0, "detailed": +0.02}

# Keep the voice intelligible whatever the combination.
PACE_MIN, PACE_MAX = 0.8, 1.25


@dataclass(frozen=True)
class VoiceParams:
    model: str
    length_scale: float
    noise_scale: float = 0.667   # Piper's defaults
    noise_w: float = 0.8

    def synthesis_kwargs(self) -> dict[str, float]:
        """Keyword arguments accepted by PiperVoice.synthesize()."""
        return {
            "length_scale": self.length_scale,
            "noise_scale": self.noise_scale,
            "noise_w": self.noise_w,
        }


def voice_params(settings: TotSettings, model: str | None = None) -> VoiceParams:
    """Derive Piper parameters from a student's settings."""
    pace = (
        1.0
        + _ARM_PACE.get(settings.encouragement_arm, 0.0)
        + _WRONG_ANSWER_PACE.get(settings.wrong_answer_style, 0.0)
        + _LENGTH_PACE.get(settings.response_length, 0.0)
    )
    pace = max(PACE_MIN, min(PACE_MAX, round(pace, 3)))
    return VoiceParams(model=model or DEFAULT_VOICE_MODEL, length_scale=pace)
