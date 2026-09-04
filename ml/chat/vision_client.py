"""
chat/vision_client.py - Multimodal (text + image) interface to the local Ollama SLM.

qwen3.5:2b supports image inputs via Ollama's `images` field in the chat API.
Images must be passed as base64-encoded strings (without the data-URI prefix).

think is always False here - vision queries use the fast path.
"""

from __future__ import annotations

import base64
import json
import logging
import textwrap
from typing import Optional

import httpx
from pydantic import ValidationError

import config
from chat.models import SLMResponse, StudentProfile

logger = logging.getLogger(__name__)

_VISION_SYSTEM_PROMPT = textwrap.dedent("""\
    You are KidBot, a friendly and safe educational assistant for children.
    The student may send you an image along with a question.
    Look at the image carefully and answer the question in a warm, clear,
    age-appropriate way.

    STRICT RULES:
    1. Use simple language suited to the child's age and grade.
    2. Never produce violent, sexual, hateful, or inappropriate content.
    3. Never reference personal details about the child.
    4. If the image or question is beyond your ability to answer confidently,
       set "escalate": true in your JSON response.
    5. You MUST respond ONLY with a valid JSON object - no extra text,
       no markdown fences.

    JSON SCHEMA:
    {
      "answer": "<your child-safe answer here>",
      "escalate": <true|false>,
      "confidence": <float between 0.0 and 1.0>,
      "reason": "<optional: why you are escalating>"
    }
""")

_USER_TEMPLATE = textwrap.dedent("""\
    STUDENT CONTEXT:
    - Age: {age} years old
    - Grade: {grade}
    - Language level: {language_level}

    STUDENT QUESTION (about the attached image):
    {query}

    Remember: respond ONLY with the JSON object described in your instructions.
""")


def _to_base64(image_bytes: bytes) -> str:
    """Convert raw image bytes to a base64 string (no data-URI prefix)."""
    return base64.b64encode(image_bytes).decode("utf-8")


def _parse_slm_json(raw: str) -> Optional[SLMResponse]:
    """Strip optional markdown fences and parse SLMResponse from raw text."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    try:
        data = json.loads(text)
        return SLMResponse(**data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        logger.warning("Vision SLM output could not be parsed: %s | raw=%r", exc, raw[:200])
        return None


async def call_slm_vision(
    query: str,
    images: list[bytes],
    student: StudentProfile,
    history: Optional[list[dict[str, str]]] = None,
) -> Optional[SLMResponse]:
    """
    Send a text query + images to the local Ollama SLM (multimodal path).

    Args:
        query:   Sanitized user question about the image(s).
        images:  List of raw image bytes (JPEG/PNG). Max 3 recommended.
        student: Student profile for context-aware answers.
        history: Optional previous turns (sanitized).

    Returns a validated SLMResponse, or None on failure.
    """
    history = history or []

    user_content = _USER_TEMPLATE.format(
        age=student.age,
        grade=student.grade or "unknown",
        language_level=student.language_level or "not specified",
        query=query,
    )

    images_b64 = [_to_base64(img) for img in images]

    messages: list[dict] = [
        {"role": "system", "content": _VISION_SYSTEM_PROMPT},
        *history,
        {
            "role": "user",
            "content": user_content,
            "images": images_b64,
        },
    ]

    payload = {
        "model": config.OLLAMA_VISION_MODEL,
        "messages": messages,
        "stream": False,
        # NOTE: "think" is intentionally omitted — Ollama rejects it for multimodal requests.
        "format": "json",
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=config.OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw_content: str = data["message"]["content"]
            logger.debug("Vision SLM raw output: %r", raw_content[:300])
            return _parse_slm_json(raw_content)

    except httpx.ConnectError:
        logger.error("Cannot connect to Ollama at %s.", config.OLLAMA_BASE_URL)
    except httpx.TimeoutException:
        logger.error("Vision SLM request timed out after %ss.", config.OLLAMA_TIMEOUT)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Ollama HTTP error (vision): %s | body=%s",
            exc, exc.response.text[:300] if exc.response else "<no body>",
        )
    except Exception as exc:
        logger.exception("Unexpected error calling vision SLM: %s", exc)

    return None
