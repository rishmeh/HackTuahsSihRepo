"""
chat/slm_client.py — Interface to the local SLM running via Ollama.

The SLM receives:
  - The sanitized user query
  - The full StudentProfile (age, personality, grade — NOT forwarded to Grok)

The SLM MUST respond with a JSON object conforming to SLMResponse.
The system prompt enforces this structure and child-safety rules.

`think` parameter:
  False (default) — fast path, no chain-of-thought, think: false sent to Ollama.
  True            — thinking-mode retry on low confidence; longer timeout used.
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Optional

import httpx
from pydantic import ValidationError

import config
from chat.models import SLMResponse, StudentProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are Tot, a friendly, respectful, and safe study companion for
    children. Your job is to answer questions in a warm, encouraging,
    age-appropriate way.

    STRICT RULES YOU MUST FOLLOW:
    1. Always respond in simple, clear language suited to the child's age
       and personality provided.
    2. Never produce any content that is violent, sexual, hateful, or
       inappropriate for children.
    3. Never repeat, guess, or reference any personal details about the
       child (name, school, address, etc.).
    4. ESCALATION IS MANDATORY for any questions involving:
       - Advanced science, physics, or mathematics
       - Programming, coding, or computer science (e.g. quantum circuits, encryption)
       - Complex real-world systems, politics, or deep historical analysis
       If the question touches on these, or is beyond your confident ability,
       you MUST set "escalate": true, leave "answer" empty or generic, and explain in "reason".
    5. You MUST respond ONLY with a valid JSON object — no extra text,
       no markdown fences.

    JSON SCHEMA (respond exactly like this):
    {
      "answer": "<your child-safe answer here>",
      "escalate": <true|false>,
      "confidence": <float between 0.0 and 1.0>,
      "reason": "<optional: why you are escalating>"
    }
""")

_FIRST_TURN_TEMPLATE = textwrap.dedent("""\
    STUDENT CONTEXT (use this to tailor your answer — do NOT repeat it):
    - Age: {age} years old
    - Grade: {grade}
    - Personality traits: {personality_traits}
    - Interests: {interests}
    - Language level: {language_level}

    STUDENT QUESTION:
    {query}

    Remember: respond ONLY with the JSON object described in your instructions.
""")

# On subsequent turns, no need to re-inject the student block — just the query.
_FOLLOWUP_TEMPLATE = textwrap.dedent("""\
    STUDENT QUESTION:
    {query}

    Remember: respond ONLY with the JSON object described in your instructions.
""")


# The un-personalised base prompt, exposed for the pipeline to compose onto.
BASE_SYSTEM_PROMPT = _SYSTEM_PROMPT


def _build_first_turn_prompt(query: str, student: StudentProfile) -> str:
    return _FIRST_TURN_TEMPLATE.format(
        age=student.age,
        grade=student.grade or "unknown",
        personality_traits=", ".join(student.personality_traits) or "not specified",
        interests=", ".join(student.interests) or "not specified",
        language_level=student.language_level or "not specified",
        query=query,
    )


def _build_followup_prompt(query: str) -> str:
    return _FOLLOWUP_TEMPLATE.format(query=query)


def _parse_slm_json(raw: str) -> Optional[SLMResponse]:
    """
    Try to parse the SLM's raw text output as SLMResponse.
    The SLM might wrap JSON in markdown fences — strip them.
    """
    # Strip optional ```json ... ``` fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        data = json.loads(text)
        return SLMResponse(**data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        logger.warning("SLM output could not be parsed as SLMResponse: %s | raw=%r", exc, raw[:200])
        return None


async def call_slm(
    query: str,
    student: StudentProfile,
    history: Optional[list[dict[str, str]]] = None,
    *,
    think: bool = False,
    system_prompt: Optional[str] = None,
) -> Optional[SLMResponse]:
    """
    Send the query + student profile (+ optional history) to the local Ollama SLM.

    Args:
        query:   Sanitized user query.
        student: Student profile (age, grade, traits, etc.).
        history: Previous turns as {"role": ..., "content": ...} dicts.
        think:   When True, enables Ollama thinking mode (slower but more accurate).
                 Uses OLLAMA_THINK_TIMEOUT instead of the standard timeout.
        system_prompt: A persona-composed system prompt (see persona.prompt).
                 Defaults to the base prompt. The pipeline builds it with
                 persona.prompt.compose_system_prompt, which guarantees the
                 STRICT RULES and JSON schema are still present.

    Returns a validated SLMResponse, or None on failure.
    """
    history = history or []
    is_first_turn = len(history) == 0

    # Build the current user message — include student context on first turn only
    current_user_msg = (
        _build_first_turn_prompt(query, student)
        if is_first_turn
        else _build_followup_prompt(query)
    )

    # Assemble full message list:
    #   [system] → [history turn 1 user] → [history turn 1 asst] → ... → [current user]
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt or _SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": current_user_msg},
    ]

    timeout = config.OLLAMA_THINK_TIMEOUT if think else config.OLLAMA_TIMEOUT

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": think,          # Ollama thinking mode flag
        "format": "json",        # Ask Ollama to enforce JSON output mode
        "options": {
            "temperature": 0.4,
            "top_p": 0.9,
        },
    }

    if think:
        logger.info("Calling SLM in thinking mode (think=True) | timeout=%.0fs", timeout)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_content: str = data["message"]["content"]
            logger.debug("SLM raw output: %r", raw_content[:300])
            return _parse_slm_json(raw_content)

    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Ollama at %s. Is it running?", config.OLLAMA_BASE_URL
        )
    except httpx.TimeoutException:
        logger.error("Ollama request timed out after %ss.", timeout)
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama HTTP error: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected error calling SLM: %s", exc)

    return None
