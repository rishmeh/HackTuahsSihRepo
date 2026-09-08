"""
persona_setup/sessions.py — In-memory persona setup sessions.

One session per (profile_id, device). Tracks which question is next and the
answers collected so far. When all questions are answered it builds and saves
a real LearnerProfile via the existing learner stack.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from learner.models import LearnerProfile
from learner.profile_store import ProfileStore
from learner import config as learner_config
from persona_setup.questions import QUESTIONS, classify_answer

logger = logging.getLogger(__name__)

# In-memory store: profile_id (as str) → SetupSession
_sessions: dict[str, "SetupSession"] = {}


@dataclass
class SetupSession:
    profile_id: str
    age: int
    current_idx: int = 0
    answers: dict[str, str] = field(default_factory=dict)
    retries: int = 0          # consecutive unrecognised answers for current Q

    @property
    def done(self) -> bool:
        return self.current_idx >= len(QUESTIONS)

    def current_question(self) -> dict | None:
        if self.done:
            return None
        return QUESTIONS[self.current_idx]

    def submit_answer(self, raw: str) -> tuple[bool, str]:
        """
        Process a raw transcript for the current question.

        Returns:
            (accepted, reply_text)
            accepted=True  → answer was recognised; reply is the next question
                             or the completion message.
            accepted=False → answer was not recognised; reply asks again.
        """
        q = self.current_question()
        if q is None:
            return True, "Your persona is already set up!"

        value = classify_answer(q, raw)
        if value is None:
            self.retries += 1
            if self.retries >= 2:
                # After two failures use the first (safe default) option
                value = q["options"][0]
                logger.info(
                    "Persona setup: unrecognised answer for %r twice; defaulting to %r",
                    q["id"], value,
                )
                self.retries = 0
            else:
                opts = _option_hint(q)
                return False, f"Sorry, I didn't catch that. {opts}"

        self.answers[q["id"]] = value
        self.retries = 0
        self.current_idx += 1

        if self.done:
            return True, _save_and_confirm(self)
        else:
            nq = self.current_question()
            return True, nq["ask"] if nq else ""


def _option_hint(q: dict) -> str:
    return f"Please say {q['ask'].split('Say ')[-1]}"


def _save_and_confirm(session: SetupSession) -> str:
    """Build a LearnerProfile from the collected answers and persist it."""
    profile = _build_profile(session.age, session.answers)
    store = ProfileStore(learner_config.LEARNER_DB_PATH)
    store.save(session.profile_id, profile)
    logger.info("Persona saved for profile_id=%r answers=%s", session.profile_id, session.answers)

    tone = session.answers.get("tone", "warm")
    mode = session.answers.get("persona_mode", "teacher")
    fmt  = session.answers.get("explanation_format", "narrative")
    return (
        f"Perfect! I've saved your persona. "
        f"I'll be your {mode}, explain things through {fmt.replace('_', ' ')}, "
        f"and keep a {'playful' if tone == 'playful' else 'professional'} tone. "
        "You're all set — just talk to me normally from now on!"
    )


def _build_profile(age: int, answers: dict) -> LearnerProfile:
    """Convert conversational answers into a scored LearnerProfile."""
    fmt       = answers.get("explanation_format", "narrative")
    length    = answers.get("response_length", "normal")
    wrong     = answers.get("wrong_answer_style", "supportive")
    pmode     = answers.get("persona_mode", "teacher")
    motiv     = answers.get("motivation", "curiosity")
    tone      = answers.get("tone", "playful")

    def _dist(value: str, keys: list[str]) -> dict[str, float]:
        """Put 1.0 on the chosen value, distribute 0.0 to others."""
        return {k: (1.0 if k == value else 0.0) for k in keys}

    preferences = {
        "explanation_format": _dist(fmt, ["narrative", "structural", "concise", "socratic"]),
        "persona_mode":       _dist(pmode, ["teacher", "peer", "socratic", "independent"]),
        "motivation":         _dist(motiv, ["curiosity", "utility", "gap", "mastery"]),
        # These weren't asked; keep neutral
        "orientation": {v: 0.25 for v in ["overview", "explore", "social", "goal"]},
        "skill_intro":  {v: 0.25 for v in ["observe", "trial", "steps", "guided"]},
    }

    # Map wrong-answer style to failure_sensitivity
    fs = {"gentle": 0.75, "supportive": 0.5, "analytical": 0.25}[wrong]
    traits = {
        "failure_sensitivity":    fs,
        "frustration_tolerance":  1.0 - fs,
        "help_seeking":           0.7 if pmode in ("teacher", "socratic") else 0.4,
        "confidence_expression":  0.3 if fs >= 0.7 else 0.65,
        "social_orientation":     0.7 if tone == "playful" else 0.4,
    }

    constraints: list[str] = []
    if length == "terse":
        constraints.append("brevity")
    if tone == "plain":
        constraints.append("low_stakes")
    if length == "detailed":
        constraints.append("explain_why")
    if tone == "playful":
        constraints.append("playful")

    return LearnerProfile(
        questionnaire_version=2,          # voice setup version
        age=age,
        preferences=preferences,
        traits=traits,
        constraints=constraints,
        confidence={k: 0.9 for k in preferences},
        answers={i: list(answers.values())[i] for i in range(len(answers))},
        answered=len(answers),
        skipped=[],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(profile_id: str, age: int) -> str:
    """Begin a new persona setup session. Returns the first question."""
    session = SetupSession(profile_id=profile_id, age=age)
    _sessions[profile_id] = session
    intro = (
        "Let's set up your persona — I'll ask you six quick questions. "
        "You can say a letter or just describe what you prefer. "
        "Say 'skip' at any time to use the default for that question. "
        + QUESTIONS[0]["ask"]
    )
    return intro


def answer(profile_id: str, raw: str, age: int = 10) -> tuple[bool, str, bool]:
    """
    Submit an answer to the current question.

    Returns (accepted, reply_text, complete).
    """
    if profile_id not in _sessions:
        # Auto-start if not yet initialised
        start(profile_id, age)

    session = _sessions[profile_id]

    # Handle skip
    if "skip" in raw.lower():
        # Use the first (safe default) option
        q = session.current_question()
        if q:
            session.answers[q["id"]] = q["options"][0]
            session.current_idx += 1
        if session.done:
            del _sessions[profile_id]
            return True, _save_and_confirm(session), True
        nq = session.current_question()
        return True, nq["ask"] if nq else "", False

    accepted, reply = session.submit_answer(raw)
    complete = session.done and accepted
    if complete:
        _sessions.pop(profile_id, None)
    return accepted, reply, complete


def is_active(profile_id: str) -> bool:
    return profile_id in _sessions


def cancel(profile_id: str) -> bool:
    """Discard an in-progress setup without changing the saved persona."""
    return _sessions.pop(profile_id, None) is not None
