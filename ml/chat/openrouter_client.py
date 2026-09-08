"""
chat/openrouter_client.py — Interface to the OpenRouter API.

CRITICAL INVARIANT: This module MUST NEVER receive or forward:
  - Student name
  - Student age
  - Student school / location
  - Any other PII from the StudentProfile

It receives ONLY the sanitized query string.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for OpenRouter — child-safe, no personalisation
# ---------------------------------------------------------------------------

_OPENROUTER_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a helpful, respectful educational assistant designed to help
    children learn. Your answers must be:
      - Age-appropriate and free of any adult, violent, or harmful content
      - Clear, educational, and encouraging
      - Concise (no more than a few paragraphs)
      - Written in plain English

    You do NOT know who the student is. Keep answers general and safe.
    Never ask for personal information. Never produce harmful content.
""")


async def call_openrouter(
    sanitized_query: str,
    history: Optional[list[dict[str, str]]] = None,
    *,
    system_prompt: Optional[str] = None,
) -> Optional[str]:
    """
    Send the *already-sanitized* query (+ optional history) to OpenRouter.

    ``system_prompt`` may be the locally generated, policy-derived Tot prompt.
    It contains no student identity or raw questionnaire answers.

    history: list of {"role": "user"|"assistant", "content": "..."} dicts.
             All entries are already sanitized and safety-filtered, so it
             is safe to forward them to the external API.

    This function deliberately accepts only plain strings (no StudentProfile)
    to enforce the PII boundary at the type level.

    Returns the answer string, or None on failure.
    """
    if not config.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set. Cannot call OpenRouter API.")
        return None

    history = history or []
    query = sanitized_query[: config.MAX_QUERY_LENGTH]

    prompt = system_prompt or _OPENROUTER_SYSTEM_PROMPT
    messages: list[dict[str, str]] = [
        {"role": "system", "content": prompt},
        *history,
        {"role": "user", "content": query},
    ]

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.5,
    }

    try:
        async with httpx.AsyncClient(timeout=config.OPENROUTER_TIMEOUT) as client:
            response = await client.post(
                f"{config.OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            answer: str = data["choices"][0]["message"]["content"].strip()
            logger.debug("OpenRouter response (first 200 chars): %r", answer[:200])
            return answer

    except httpx.ConnectError:
        logger.error("Cannot connect to OpenRouter API at %s.", config.OPENROUTER_BASE_URL)
    except httpx.TimeoutException:
        logger.error("OpenRouter API request timed out after %ss.", config.OPENROUTER_TIMEOUT)
    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter API HTTP error %s: %s", exc.response.status_code, exc)
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected OpenRouter API response structure: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected error calling OpenRouter: %s", exc)

    return None
