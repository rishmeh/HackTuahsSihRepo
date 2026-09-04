"""
quiz/generator.py — Orchestrates the full quiz generation workflow.

  QuizRequest
      │
      ▼
  [openrouter_quiz_client] ← calls OpenRouter API
      │
      ▼
  [template.parse_quiz_from_json] ← validates & builds Quiz model
      │
      ▼
  Quiz object (or raises RuntimeError)
"""

from __future__ import annotations

import logging

from quiz.models import Quiz, QuizRequest
from quiz.openrouter_quiz_client import generate_quiz_via_openrouter
from quiz.template import format_quiz, parse_quiz_from_json

logger = logging.getLogger(__name__)


async def generate_quiz(req: QuizRequest) -> Quiz:
    """
    Generate a validated Quiz for the given QuizRequest.

    Raises:
        RuntimeError: If the SLM fails or returns unparseable output.
    """
    logger.info(
        "Generating %d-question quiz | subject=%r | topics=%s",
        req.num_questions,
        req.subject,
        req.student.covered_topics,
    )

    raw = await generate_quiz_via_openrouter(req)
    if raw is None:
        raise RuntimeError(
            "Quiz generation failed — check if OpenRouter API key is valid and network is up."
        )

    quiz = parse_quiz_from_json(
        raw=raw,
        expected_count=req.num_questions,
        student=req.student,
        subject=req.subject,
    )

    if quiz is None:
        raise RuntimeError(
            "OpenRouter returned a quiz that could not be parsed or validated. "
            "Check the OpenRouter API output format."
        )

    logger.info("Quiz generated successfully: %s (%d questions)", quiz.quiz_id, quiz.num_questions)
    return quiz


async def generate_and_format_quiz(req: QuizRequest) -> tuple[Quiz, str]:
    """
    Convenience wrapper that returns both the Quiz object and
    the formatted human-readable string.
    """
    quiz = await generate_quiz(req)
    formatted = format_quiz(quiz)
    return quiz, formatted
