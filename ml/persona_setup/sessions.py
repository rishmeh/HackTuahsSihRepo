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
    from learner.scoring import score_answers
    from learner.questionnaire import load_questionnaire

    q = load_questionnaire()
    profile = score_answers(session.answers, session.age, q)
    
    store = ProfileStore(learner_config.LEARNER_DB_PATH)
    store.save(session.profile_id, profile)
    logger.info("Persona saved for profile_id=%r answers=%s", session.profile_id, session.answers)

    # Pick a couple of top preferences to mention
    fmt = profile.top("explanation_format") or "narrative"
    mode = profile.top("persona_mode") or "teacher"
    
    # We don't have tone directly anymore, we have traits and constraints.
    playful = "playful" in profile.constraints
    
    return (
        f"Perfect! I've saved your persona. "
        f"I'll be your {mode}, explain things through {fmt.replace('_', ' ')}, "
        f"and keep a {'playful' if playful else 'professional'} tone. "
        "You're all set — just talk to me normally from now on!"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(profile_id: str, age: int) -> str:
    """Begin a new persona setup session. Returns the first question."""
    session = SetupSession(profile_id=profile_id, age=age)
    _sessions[profile_id] = session
    intro = (
        "Let's set up your persona — I'll ask you ten quick questions. "
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
