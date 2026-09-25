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

Warm-loading:
  A single persistent httpx.AsyncClient is created at import time and reused
  for every request so that TCP connections are kept alive.  call warm_slm()
  once at startup; it issues a no-op generate request with keep_alive="-1"
  so Ollama loads the model weights into memory before the first real query.

Streaming (voice path):
  stream_slm_voice() is an async generator that streams plain-text tokens
  from Ollama and yields sentence-boundary chunks suitable for live TTS.
  It does NOT use JSON mode — the voice system prompt produces plain prose.
"""

from __future__ import annotations

import json
import logging
import re
import textwrap
from typing import AsyncIterator, Optional

import httpx
from pydantic import ValidationError

import config
from chat.models import SLMResponse, StudentProfile

logger = logging.getLogger(__name__)

# Sentence-boundary splitter: split AFTER .  !  ?  (keeping the punctuation
# attached to the preceding text, never as a standalone chunk).
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

# ---------------------------------------------------------------------------
# Persistent HTTP client — created once, reused forever.
# Never closed so that Ollama connections stay alive across requests.
# ---------------------------------------------------------------------------

_http_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Return (or lazily create) the module-level persistent httpx client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=config.OLLAMA_THINK_TIMEOUT,   # worst-case read budget
                write=10.0,
                pool=5.0,
            ),
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )
        logger.info("Created new persistent httpx client for Ollama.")
    return _http_client


# ---------------------------------------------------------------------------
# System prompt template (JSON pipeline path)
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

# Voice-path system prompt — plain prose, no JSON, optimised for TTS streaming.
_VOICE_SYSTEM_PROMPT = textwrap.dedent("""\
    You are Tot, a friendly and safe study companion for children.
    Answer questions warmly and clearly in 2–4 sentences.
    Use simple words suited to the child's age.
    Never mention violence, adult content, or personal details.
    Respond with plain sentences only — no bullet points, no markdown,
    no JSON. Your words will be read aloud, so keep them conversational.
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

# Voice-path turn template — no JSON reminder.
_VOICE_TURN_TEMPLATE = textwrap.dedent("""\
    STUDENT CONTEXT:
    - Age: {age} years old
    - Grade: {grade}

    STUDENT QUESTION:
    {query}
""")


# The un-personalised base prompt, exposed for the pipeline to compose onto.
BASE_SYSTEM_PROMPT = _SYSTEM_PROMPT

# Sentence-boundary splitter: split after . ! ? followed by space/end.
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


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


# ---------------------------------------------------------------------------
# Warm-loading
# ---------------------------------------------------------------------------

async def warm_slm() -> None:
    """
    Pre-load the SLM into Ollama's memory so the first real query has no
    cold-start delay.  Sends a minimal generate request with keep_alive="-1"
    which tells Ollama to keep the model resident until the process exits.

    Call this once from the FastAPI startup handler.
    """
    logger.info("Warming SLM model '%s' (keep_alive=%s)…", config.OLLAMA_MODEL, config.SLM_KEEP_ALIVE)
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": "",           # empty prompt — Ollama loads and immediately returns
        "stream": False,
        "keep_alive": config.SLM_KEEP_ALIVE,
    }
    try:
        client = _get_client()
        resp = await client.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
        )
        resp.raise_for_status()
        logger.info("SLM warm-load complete — model is resident in memory.")
    except httpx.ConnectError:
        logger.warning(
            "warm_slm: Could not reach Ollama at %s. "
            "Model will cold-start on first query.",
            config.OLLAMA_BASE_URL,
        )
    except Exception as exc:
        logger.warning("warm_slm: Unexpected error (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Standard (JSON-mode) SLM call — used by the chat pipeline
# ---------------------------------------------------------------------------

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
        "keep_alive": config.SLM_KEEP_ALIVE,  # never evict
        "options": {
            "temperature": 0.4,
            "top_p": 0.9,
        },
    }

    if think:
        logger.info("Calling SLM in thinking mode (think=True) | timeout=%.0fs", timeout)

    try:
        client = _get_client()
        response = await client.post(
            f"{config.OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=5.0),
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


# ---------------------------------------------------------------------------
# Streaming voice path — yields sentence chunks as they arrive
# ---------------------------------------------------------------------------

async def stream_slm_voice(
    query: str,
    student: StudentProfile,
    history: Optional[list[dict[str, str]]] = None,
    *,
    system_prompt: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Stream plain-text tokens from Ollama and yield *sentence-boundary chunks*
    so the caller can pipe each chunk to TTS the moment it is complete.

    Unlike call_slm() this uses:
      - stream=True         (ndjson token-by-token response)
      - No JSON format mode (produces natural prose, not a JSON object)
      - _VOICE_SYSTEM_PROMPT (TTS-friendly plain-sentence instructions)

    Yields:
        Non-empty strings, each containing one or more complete sentences
        (or a final partial sentence when the model finishes mid-sentence).

    Usage::
        async for chunk in stream_slm_voice(query, student):
            speak_text(chunk)   # feed to TTS immediately
    """
    history = history or []
    age = student.age
    grade = student.grade or f"grade {max(1, age - 5)}"

    # Inject student context into the first user message only.
    if history:
        user_content = query
    else:
        user_content = _VOICE_TURN_TEMPLATE.format(
            age=age, grade=grade, query=query
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt or _VOICE_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_content},
    ]

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,              # never think on the voice path — latency matters
        "keep_alive": config.SLM_KEEP_ALIVE,   # never evict
        "options": {
            "temperature": 0.5,
            "top_p": 0.9,
        },
    }

    buffer = ""
    try:
        client = _get_client()
        async with client.stream(
            "POST",
            f"{config.OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=httpx.Timeout(
                connect=10.0,
                read=config.OLLAMA_TIMEOUT,
                write=10.0,
                pool=5.0,
            ),
        ) as response:
            response.raise_for_status()

            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                # Ignore thinking tokens (present when think=True)
                token: str = event.get("message", {}).get("content", "")
                if not token:
                    # model signalled done
                    if event.get("done"):
                        break
                    continue

                buffer += token

                # Split on sentence-ending whitespace (after . ! ?).
                # The lookbehind keeps punctuation attached to its sentence.
                parts = _SENTENCE_END.split(buffer)
                while len(parts) > 1:
                    sentence = parts[0].strip()
                    parts = parts[1:]
                    buffer = "".join(parts)
                    if len(sentence) >= 4:  # skip lone punctuation fragments
                        logger.debug("Voice stream chunk: %r", sentence[:80])
                        yield sentence

                # Fallback: no sentence boundary but buffer is getting long.
                # Only flush at a word boundary to avoid cutting mid-word.
                if len(buffer) >= config.SLM_VOICE_CHUNK_CHARS:
                    # Find last space to cut at a word boundary
                    cut = buffer.rfind(' ')
                    if cut > 0:
                        chunk, buffer = buffer[:cut].strip(), buffer[cut:].lstrip()
                        if chunk:
                            logger.debug("Voice stream flush (long buffer): %r", chunk[:80])
                            yield chunk

    except httpx.ConnectError:
        logger.error("stream_slm_voice: Cannot connect to Ollama at %s.", config.OLLAMA_BASE_URL)
        return
    except httpx.TimeoutException:
        logger.error("stream_slm_voice: Stream timed out.")
        return
    except httpx.HTTPStatusError as exc:
        logger.error("stream_slm_voice: Ollama HTTP error: %s", exc)
        return
    except Exception as exc:
        logger.exception("stream_slm_voice: Unexpected error: %s", exc)
        return

    # Flush any remaining text (last partial sentence).
    if buffer.strip():
        logger.debug("Voice stream final flush: %r", buffer[:80])
        yield buffer.strip()
