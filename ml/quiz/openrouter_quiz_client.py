"""
quiz/openrouter_quiz_client.py — Calls the OpenRouter API to generate high-quality quizzes.

This replaces the SLM for quiz generation to ensure high-quality, accurate,
and grade-aligned content. OpenRouter first considers standard curriculum details
for the given grade and subject, pairs it with the student's covered topics,
and generates the quiz.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Optional

import httpx

import config
from quiz.models import QuizRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for quiz generation via OpenRouter
# ---------------------------------------------------------------------------

_QUIZ_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert educational curriculum designer and quiz creator.
    Your task is to create highly accurate, engaging, and age-appropriate quizzes.
    
    INSTRUCTIONS:
    1. First, silently recall the standard educational curriculum for the specified grade and subject.
    2. Then, pair those standard curriculum details with the specific "covered_topics" provided for the student.
    3. Generate a quiz that accurately reflects this tailored curriculum.
    
    STRICT OUTPUT RULES:
    1. Respond ONLY with a valid JSON object — no extra text, no markdown formatting outside the JSON block.
    2. Use ONLY these question types: "multiple_choice", "true_false", "fill_blank", "short_answer".
    3. For "multiple_choice" questions you MUST include an "options" list of exactly 4 choices.
    4. Every question must have: id (integer), type, difficulty ("easy", "medium", "hard"), question, answer, and optionally explanation.
    5. Difficulty distribution: mix of easy, medium, and hard questions.
    6. Language and complexity must be perfectly aligned with the student's age and grade.
    7. NEVER include violent, adult, or inappropriate content.

    JSON SCHEMA (output this exact structure):
    {
      "questions": [
        {
          "id": 1,
          "type": "multiple_choice",
          "difficulty": "easy",
          "question": "...",
          "options": ["Option A", "Option B", "Option C", "Option D"],
          "answer": "Option A",
          "explanation": "..."
        }
      ]
    }
""")

_QUIZ_USER_PROMPT_TEMPLATE = textwrap.dedent("""\
    Create exactly {num_questions} quiz questions for the following student profile:

    - Age: {age} years old
    - Grade: {grade}
    - Personality / learning style: {personality_traits}
    - Subject: {subject}
    - Specific topics they have covered: {covered_topics}

    Requirements:
    - Generate exactly {num_questions} questions.
    - Mix question types: multiple_choice, true_false, fill_blank, short_answer.
    - Ensure factual accuracy and high educational value.
    - For multiple_choice, always provide exactly 4 distinct options.
    - Provide a brief, helpful explanation for the correct answer.

    Respond ONLY with the raw JSON object. Do not include ```json fences or any conversational text.
""")


def _build_quiz_prompt(req: QuizRequest) -> str:
    return _QUIZ_USER_PROMPT_TEMPLATE.format(
        num_questions=req.num_questions,
        age=req.student.age,
        grade=req.student.grade or "not specified",
        personality_traits=", ".join(req.student.personality_traits) or "not specified",
        subject=req.subject,
        covered_topics=", ".join(req.student.covered_topics),
    )


async def generate_quiz_via_openrouter(req: QuizRequest) -> Optional[str]:
    """
    Ask the OpenRouter API to generate a high-quality quiz JSON string.
    
    Returns the raw string from OpenRouter (to be parsed by template.py),
    or None on failure.
    """
    if not config.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set. Cannot use OpenRouter for quiz generation.")
        return None

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _QUIZ_SYSTEM_PROMPT},
            {"role": "user", "content": _build_quiz_prompt(req)},
        ],
        "max_tokens": 2000,
        "temperature": 0.5,
    }

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.OPENROUTER_TIMEOUT * 2) as client:
            response = await client.post(
                f"{config.OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            raw: str = data["choices"][0]["message"]["content"]
            logger.debug("OpenRouter quiz raw output (first 500): %r", raw[:500])
            return raw

    except httpx.ConnectError:
        logger.error("Cannot connect to OpenRouter API at %s for quiz generation.", config.OPENROUTER_BASE_URL)
    except httpx.TimeoutException:
        logger.error("OpenRouter quiz request timed out.")
    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter HTTP error during quiz: %s %s", exc.response.status_code, exc.response.text)
    except Exception as exc:
        logger.exception("Unexpected error in quiz OpenRouter call: %s", exc)

    return None
