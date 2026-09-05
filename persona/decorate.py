"""
persona/decorate.py — Wraps an SLM answer in Tot's voice.

The model produced the content. This adds the line before or after it that
carries the personality, chosen by the student's settings and by what kind
of moment this is.

Two rules override everything else:

  * A student who asked Tot to get to the point (response_length == "terse")
    gets the bare answer — except on a wrong answer, where the gentle line
    is not optional. Brevity is a preference; kindness on failure is not.
  * Wrong answers never receive a sarcastic line. PhraseBook guarantees it.
"""

from __future__ import annotations

from learner.models import TotSettings
from persona.phrases import PhraseBook, Situation

# Situations answered with an opener from the encouragement pool.
_ENCOURAGE = {Situation.STRUGGLING, Situation.REPEATED_QUESTION, Situation.IDLE}

# Situations whose opener comes from a pool of the same name.
_NAMED_OPENERS = {
    Situation.GREETING: "greeting",
    Situation.LISTENING: "listening",
    Situation.THINKING: "thinking",
    Situation.ERROR: "error",
}


def decorate_answer(
    answer: str,
    settings: TotSettings,
    situation: Situation,
    book: PhraseBook,
) -> str:
    """
    Return the answer with Tot's opener and/or closer for this moment.

    The answer text itself is always preserved verbatim.
    """
    if not answer:
        return answer

    arm = settings.encouragement_arm
    allow = settings.sarcasm_allowed

    if situation is Situation.WRONG_ANSWER:
        opener = book.wrong_answer(style=settings.wrong_answer_style, sarcasm_allowed=allow)
        return f"{opener}\n{answer}"

    if settings.response_length == "terse":
        return answer

    if situation is Situation.CORRECT_ANSWER:
        opener = book.pick("celebration", arm=arm, situation=situation, sarcasm_allowed=allow)
        return f"{opener}\n{answer}"

    if situation in _ENCOURAGE:
        opener = book.pick("encouragement", arm=arm, situation=situation, sarcasm_allowed=allow)
        return f"{opener}\n{answer}"

    if situation in _NAMED_OPENERS:
        opener = book.pick(_NAMED_OPENERS[situation], arm=arm, situation=situation, sarcasm_allowed=allow)
        return f"{opener}\n{answer}"

    # A plain question: answer first, then a short hand-back.
    closer = book.pick("signoff", arm=arm, situation=situation, sarcasm_allowed=allow)
    return f"{answer}\n{closer}"
