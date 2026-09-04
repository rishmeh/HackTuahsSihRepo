"""
quiz/template.py — Quiz formatting and validation utilities.

Responsibilities:
  - Parse raw JSON from the SLM into validated Quiz objects.
  - Format a Quiz into a clean, human-readable string.
  - Enforce question-count bounds (5–10).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import ValidationError

from quiz.models import Quiz, QuizQuestion, QuizStudentProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_quiz_from_json(raw: str, expected_count: int, student: QuizStudentProfile, subject: str) -> Optional[Quiz]:
    """
    Parse the SLM's raw JSON output into a validated Quiz.

    Returns a Quiz on success, or None if parsing / validation fails.
    """
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Quiz JSON parse error: %s | raw (first 300): %r", exc, raw[:300])
        return None

    # Allow SLM to return either {"questions": [...]} or [...] directly
    questions_raw: list = []
    if isinstance(data, list):
        questions_raw = data
    elif isinstance(data, dict) and "questions" in data:
        questions_raw = data["questions"]
    else:
        logger.error("Unexpected quiz JSON structure: %s", type(data))
        return None

    # Enforce count bounds
    questions_raw = questions_raw[:10]  # never more than 10
    if len(questions_raw) < 5:
        logger.error("SLM returned fewer than 5 questions (%d).", len(questions_raw))
        return None

    # Re-number question IDs to guarantee sequential ordering
    parsed_questions: list[QuizQuestion] = []
    for idx, q_data in enumerate(questions_raw, start=1):
        if isinstance(q_data, dict):
            q_data["id"] = idx
        try:
            parsed_questions.append(QuizQuestion(**q_data))
        except (ValidationError, TypeError) as exc:
            logger.warning("Skipping malformed question %d: %s", idx, exc)

    if len(parsed_questions) < 5:
        logger.error(
            "After validation, fewer than 5 valid questions remain (%d).",
            len(parsed_questions),
        )
        return None

    actual_count = len(parsed_questions)

    try:
        quiz = Quiz(
            subject=subject,
            grade_level=student.grade,
            num_questions=actual_count,
            questions=parsed_questions,
        )
        return quiz
    except ValidationError as exc:
        logger.error("Quiz model validation error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Formatting — human-readable text output
# ---------------------------------------------------------------------------

_QUESTION_TYPE_LABELS = {
    "multiple_choice": "Multiple Choice",
    "true_false": "True / False",
    "fill_blank": "Fill in the Blank",
    "short_answer": "Short Answer",
}

_OPTION_LABELS = ["A", "B", "C", "D", "E"]


def format_quiz(quiz: Quiz) -> str:
    """
    Render a Quiz as a clean, human-readable string.
    """
    lines: list[str] = [
        f"{'=' * 60}",
        f"  QUIZ: {quiz.subject.upper()}",
        f"  Grade: {quiz.grade_level or 'N/A'}",
        f"  Questions: {quiz.num_questions}",
        f"  Quiz ID: {quiz.quiz_id}",
        f"  Generated: {quiz.generated_at}",
        f"{'=' * 60}",
        "",
    ]

    for q in quiz.questions:
        type_label = _QUESTION_TYPE_LABELS.get(q.type, q.type)
        lines.append(f"Q{q.id}. [{type_label}] [{q.difficulty.upper()}]")
        lines.append(f"   {q.question}")

        if q.type == "multiple_choice" and q.options:
            for label, option in zip(_OPTION_LABELS, q.options):
                lines.append(f"     {label}) {option}")

        lines.append(f"   ✓ Answer: {q.answer}")

        if q.explanation:
            lines.append(f"   💡 {q.explanation}")

        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
