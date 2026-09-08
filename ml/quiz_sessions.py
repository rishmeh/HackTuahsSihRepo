"""
quiz_sessions.py — Interactive voice quiz session manager.

Maintains a per-profile quiz session that the voice agent routes through.
When a session is active every utterance is treated as an answer, not a command.

Usage:
    from quiz_sessions import sessions

    # Start a quiz (returns the first question as a spoken string)
    first_q = sessions.start(profile_key, questions)

    # Check if a session is active
    if sessions.is_active(profile_key):
        reply, done = sessions.answer(profile_key, user_text)
        speak(reply)

    # Cancel mid-session
    sessions.cancel(profile_key)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional
import re

logger = logging.getLogger(__name__)

ML_BASE = "http://127.0.0.1:8000"


@dataclass
class QuizSession:
    profile_key: str
    topic: str
    questions: list[dict]
    current: int = 0
    score: int = 0
    awaiting_answer: bool = True


import json
import httpx
import asyncio

def _grade_answer(user_text: str, question: dict) -> bool:
    """Intelligently grade the student's answer using the local Ollama model."""
    correct_ans = str(question.get("answer", "")).strip()
    q_text = question.get("question", "")
    
    # Fast path: exact match
    if user_text.strip().lower() == correct_ans.lower():
        return True
        
    prompt = f"""You are grading a quiz for a child.
Question: {q_text}
Correct Answer: {correct_ans}
Student's Answer: {user_text}

Did the student get the question right? Account for speech-to-text transcription errors (e.g., 'two' for 2, or 'sous vide' as noise).
Respond ONLY with a valid JSON object: {{"correct": true}} or {{"correct": false}}"""

    import config
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0},
        "stream": False,
        "format": "json"
    }
    
    try:
        r = httpx.post(f"{config.OLLAMA_BASE_URL}/api/chat", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        result = json.loads(data["message"]["content"])
        return bool(result.get("correct", False))
    except Exception as e:
        logger.error("LLM grading failed: %s. Falling back to simple matching.", e)
        # Fallback to simple matching
        text = user_text.lower()
        ans = correct_ans.lower()
        if len(ans) > 2 and (ans in text or text in ans):
            return True
        first_letter = ans[0] if ans else ""
        if re.search(rf"\b{re.escape(first_letter)}\b", text):
            return True
        return False


def _format_question(session: QuizSession) -> str:
    """Return the current question as a spoken string."""
    q = session.questions[session.current]
    n = session.current + 1
    total = len(session.questions)
    text = f"Question {n} of {total}. {q.get('question', '')}"

    options = q.get("options") or []
    if options:
        # Read out A, B, C, D options
        labels = ["A", "B", "C", "D", "E"]
        opts_text = ". ".join(f"{labels[i]}: {opt}" for i, opt in enumerate(options[:5]))
        text += f". The options are: {opts_text}."

    return text


class QuizSessionStore:
    """Thread-safe (GIL-protected) in-memory session store."""

    def __init__(self):
        self._sessions: dict[str, QuizSession] = {}

    def is_active(self, profile_key: str) -> bool:
        return profile_key in self._sessions

    def start(self, profile_key: str, topic: str, questions: list[dict]) -> str:
        """Start a new quiz session and return the first question."""
        if not questions:
            return "Sorry, I couldn't generate any quiz questions."

        session = QuizSession(
            profile_key=profile_key,
            topic=topic,
            questions=questions,
        )
        self._sessions[profile_key] = session
        return (
            f"Great! Starting a quiz on {topic}. "
            f"I'll ask you {len(questions)} questions. "
            "Say your answer aloud. "
            + _format_question(session)
        )

    def answer(self, profile_key: str, user_text: str) -> tuple[str, bool]:
        """
        Process a user answer. Returns (spoken_reply, is_done).
        When is_done is True the session has been removed.
        """
        session = self._sessions.get(profile_key)
        if not session:
            return "No active quiz session.", True

        q = session.questions[session.current]
        correct = _grade_answer(user_text, q)

        if correct:
            session.score += 1
            feedback = "Correct! "
        else:
            correct_ans = q.get("answer", "")
            feedback = f"Not quite. The answer was: {correct_ans}. "

        explanation = q.get("explanation", "")
        if explanation:
            feedback += explanation + " "

        session.current += 1

        if session.current >= len(session.questions):
            # Quiz finished
            total = len(session.questions)
            score = session.score
            topic = session.topic
            del self._sessions[profile_key]

            if score == total:
                grade_msg = "Perfect score! You really know your stuff!"
            elif score >= total * 0.75:
                grade_msg = "Great job! You're doing really well."
            elif score >= total * 0.5:
                grade_msg = "Good effort! Keep practicing and you'll get there."
            else:
                grade_msg = "Keep studying — you'll improve with practice!"

            reply = (
                f"{feedback}"
                f"Quiz complete! You scored {score} out of {total} on {topic}. "
                f"{grade_msg}"
            )

            # Try to persist the score to the dashboard DB
            try:
                import requests as _req
                _req.post(
                    f"{ML_BASE}/quiz/session-result",
                    json={
                        "profile_key": profile_key,
                        "topic": topic,
                        "score": score,
                        "total": total,
                    },
                    timeout=3,
                )
            except Exception:
                pass  # Non-critical

            return reply, True

        # More questions remain
        next_q_text = _format_question(session)
        reply = f"{feedback}{next_q_text}"
        return reply, False

    def cancel(self, profile_key: str) -> None:
        self._sessions.pop(profile_key, None)


# Module-level singleton
sessions = QuizSessionStore()
