"""
persona/phrases.py — The code-owned phrase pools that carry Tot's personality.

Every line here was written by a person, not generated. That is the point:
on a 0.6B model these are the only words guaranteed to sound like Tot.

Pools are keyed by *kind* (what moment it is) and *arm* (which encouragement
style this student gets). The arms are the choices a bandit will learn among
later, so they must sound genuinely different — a test checks that.

The sarcasm rule is enforced here, not in a prompt:

  * A phrase is either tagged sarcastic or it is not.
  * Sarcastic phrases are returned only when the student's settings allow
    sarcasm AND the situation is one where a joke lands on the *situation*
    ("fourth time on this one") rather than on the child.
  * Wrong answers and struggling are never such a situation. No path exists
    that returns a sarcastic line there.
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Optional


class Situation(str, Enum):
    GREETING = "greeting"
    QUESTION = "question"
    CORRECT_ANSWER = "correct_answer"
    WRONG_ANSWER = "wrong_answer"
    STRUGGLING = "struggling"
    REPEATED_QUESTION = "repeated_question"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    ERROR = "error"


# Situations where irony is aimed at circumstances, never at the child.
SAFE_FOR_SARCASM: frozenset[Situation] = frozenset(
    {Situation.REPEATED_QUESTION, Situation.IDLE, Situation.ERROR}
)

ARMS: tuple[str, ...] = ("warm", "playful", "challenge", "plain")
KINDS: tuple[str, ...] = (
    "greeting", "listening", "thinking", "encouragement",
    "celebration", "hint_opener", "signoff", "error",
)
WRONG_ANSWER_STYLES: tuple[str, ...] = ("gentle", "supportive", "analytical")

# (text, sarcastic)
_P = tuple[str, bool]


def _plain(*lines: str) -> list[_P]:
    return [(line, False) for line in lines]


_POOLS: dict[str, dict[str, list[_P]]] = {
    "greeting": {
        "warm": _plain(
            "Hey, good to see you. Ready when you are.",
            "There you are. Let's ease into it.",
            "Hi! Take a breath, then we'll start.",
            "Welcome back. I saved your spot.",
        ),
        "playful": _plain(
            "You're here! The books were getting lonely.",
            "Ta-da, it's you. Let's do something clever.",
            "Hello hello! Brain warmed up yet?",
            "Look who's back. The map's been waiting.",
        ),
        "challenge": _plain(
            "Good, you're here. Let's see what you've got today.",
            "Back for more? I like it.",
            "Ready? Today we go one step further than last time.",
            "You showed up. That's the hard part done.",
        ),
        "plain": _plain(
            "Hi. Ready to start.",
            "Welcome back. Picking up where we left off.",
            "Hello. Let's begin.",
            "Good to see you. Here's the plan.",
        ),
    },
    "listening": {
        "warm": _plain("I'm listening.", "Go ahead, I'm here.", "Yes? I'm all ears.", "Tell me."),
        "playful": _plain(
            "Ears on! Go for it.",
            "Listening mode: activated.",
            "Yep? Fire away.",
            "I'm listening. Very intently. Very.",
        ),
        "challenge": _plain(
            "Go on, hit me with it.",
            "Listening. Make it a good one.",
            "I'm ready. Are you?",
            "Say it.",
        ),
        "plain": _plain("Listening.", "Go ahead.", "Yes.", "I'm here."),
    },
    "thinking": {
        "warm": _plain(
            "Let me think about that with you.",
            "Good question. Give me a moment.",
            "Hmm, thinking...",
            "One sec, working it out.",
        ),
        "playful": _plain(
            "Ooh. Gears turning...",
            "Loading brilliance... please hold.",
            "Thinking face engaged.",
            "Hmm hm hm. Nearly there.",
        ),
        "challenge": _plain(
            "Good one. Let me work it out properly.",
            "Thinking. Don't get comfortable.",
            "Hm. Let me do this right.",
            "One moment. This deserves a real answer.",
        ),
        "plain": _plain("Thinking.", "One moment.", "Working on it.", "Let me check."),
    },
    "encouragement": {
        "warm": _plain(
            "You've got this. Take your time.",
            "It's okay to find this tricky. I'm with you.",
            "Slow is fine. Let's look at it together.",
            "Stuck is just the moment before it clicks.",
        ),
        "playful": [
            ("Plot twist: you're closer than you think!", False),
            ("Brains ache a bit when they grow. Good sign!", False),
            ("Wobbly start, strong finish. Let's go!", False),
            ("Fourth time on this one. The topic's getting suspicious.", True),
            ("Ah, our old friend again. It missed you.", True),
        ],
        "challenge": _plain(
            "Bet you can crack this without a hint.",
            "This one's harder. That's why it's worth it.",
            "I dare you to try one more angle.",
            "Think you can beat it? Prove it.",
        ),
        "plain": _plain(
            "Keep going. You are close.",
            "Try one more step.",
            "This is the hard part. Continue.",
            "Almost there. Stay with it.",
        ),
    },
    "celebration": {
        "warm": _plain(
            "Yes! You got it.",
            "That's it — well done.",
            "See? You did that.",
            "Lovely. That was all you.",
        ),
        "playful": _plain(
            "Boom! Nailed it!",
            "Correct! Do a tiny victory dance.",
            "Ding ding ding! That's the one!",
            "Yes! Brain: 1, Question: 0.",
        ),
        "challenge": _plain(
            "Correct. Told you.",
            "Got it. Now let's go harder.",
            "That's one. Ready for the next level?",
            "Right answer. Don't stop now.",
        ),
        "plain": _plain("Correct.", "That is right.", "Yes. Next one.", "Correct. Moving on."),
    },
    "hint_opener": {
        "warm": _plain(
            "Here's a little nudge.",
            "Small hint, no pressure:",
            "Let me point you somewhere.",
            "Try looking at it this way.",
        ),
        "playful": _plain(
            "Psst. Hint incoming.",
            "Tiny clue, big payoff:",
            "Hint delivery! Sign here.",
            "A whisper of a hint:",
        ),
        "challenge": _plain(
            "One hint. Make it count.",
            "Here's a clue — the rest is yours.",
            "Nudge, not an answer:",
            "I'll open the door. You walk through.",
        ),
        "plain": _plain("Hint:", "Consider this.", "A clue.", "Look here."),
    },
    "signoff": {
        "warm": _plain(
            "Ask me anything else, anytime.",
            "Hope that helps. I'm right here.",
            "Want me to go slower on any part?",
            "There when you need me.",
        ),
        "playful": _plain(
            "Questions welcome. Snacks also welcome.",
            "More where that came from!",
            "Curious for more? Same.",
            "That was fun. Next?",
        ),
        "challenge": _plain(
            "Now try explaining it back to me.",
            "Got it? Prove it with a question.",
            "Your turn — push it further.",
            "Follow-up? I'm ready.",
        ),
        "plain": _plain("Anything else.", "Next question when ready.", "That is the answer.", "Ask if unclear."),
    },
    "error": {
        "warm": _plain(
            "Something on my end went wrong. Let me try again.",
            "My mistake — give me a second.",
            "That didn't work on my side. One more go.",
            "Hmm, I slipped. Let me sort it.",
        ),
        "playful": [
            ("My circuits did a little somersault. Retrying!", False),
            ("Oops, my bad. Rebooting my dignity.", False),
            ("I blame my wires. Trying again.", False),
            ("Well. That went brilliantly on my end. Again.", True),
        ],
        "challenge": _plain(
            "My error, not yours. Let me fix it.",
            "That's on me. Again.",
            "Glitch on my side. Hold on.",
            "My fault. Recovering.",
        ),
        "plain": _plain("Error on my side. Retrying.", "My mistake. One moment.", "Something failed on my end.", "Retrying."),
    },
}

# How Tot reacts to a wrong answer, by the student's wrong_answer_style.
# Deliberately not keyed by arm and deliberately containing nothing sarcastic:
# a wrong answer is the one moment where the arm must not sharpen the tone.
_WRONG_ANSWER: dict[str, list[str]] = {
    "gentle": [
        "Not quite — and that's completely fine. Let's look together.",
        "Close, and a really normal place to land. Here's the piece that's missing.",
        "That's a common one. No worries at all — let me show you.",
        "Good try. Let's untangle it gently.",
    ],
    "supportive": [
        "Not this time, but I can see the thinking. Here's the fix.",
        "Good effort. Let's correct one part.",
        "Almost. Here's what to adjust.",
        "Not quite. You're on the right track though.",
    ],
    "analytical": [
        "Interesting — that answer is tempting, and here's exactly why it isn't right.",
        "Not correct, and the reason is worth understanding.",
        "Wrong, but usefully wrong. Let's see where it came from.",
        "No — and the 'why not' is the interesting bit.",
    ],
}

_SARCASTIC: frozenset[str] = frozenset(
    text for arms in _POOLS.values() for pool in arms.values() for text, sarcastic in pool if sarcastic
)


class PhraseBook:
    """
    Chooses phrases for a moment, honouring the sarcasm rule and avoiding
    immediate repeats.

    Args:
        rng: Injected so tests are deterministic. Defaults to a fresh Random.
    """

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self._last: dict[tuple[str, str], str] = {}

    @staticmethod
    def pool(kind: str, arm: str) -> list[str]:
        """Every phrase for a kind and arm, sarcastic ones included."""
        return [text for text, _ in _POOLS[kind][arm]]

    @staticmethod
    def is_sarcastic(phrase: str) -> bool:
        return phrase in _SARCASTIC

    def pick(self, kind: str, *, arm: str, situation: Situation, sarcasm_allowed: bool) -> str:
        """
        One phrase for this moment.

        Sarcastic candidates are removed unless the settings allow sarcasm AND
        the situation is in SAFE_FOR_SARCASM. Both conditions, always.
        """
        allow_sarcasm = sarcasm_allowed and situation in SAFE_FOR_SARCASM
        candidates = [
            text for text, sarcastic in _POOLS[kind][arm] if allow_sarcasm or not sarcastic
        ]
        return self._choose(candidates, key=(kind, arm))

    def wrong_answer(self, *, style: str, sarcasm_allowed: bool = False) -> str:
        """
        The line that precedes a correction. Never sarcastic, whatever the
        gate says — the parameter exists so callers can pass settings through
        uniformly, and so the guarantee is visible at the call site.
        """
        del sarcasm_allowed  # intentionally ignored: see docstring
        return self._choose(list(_WRONG_ANSWER[style]), key=("wrong_answer", style))

    def _choose(self, candidates: list[str], *, key: tuple[str, str]) -> str:
        if not candidates:
            raise ValueError(f"no phrases available for {key}")
        last = self._last.get(key)
        options = [c for c in candidates if c != last] if len(candidates) > 1 else candidates
        chosen = self._rng.choice(options)
        self._last[key] = chosen
        return chosen
