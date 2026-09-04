"""
chat/session_store.py — In-memory conversation history store.

Stores the last N turns per session_id so that both the SLM and
Grok API receive the full conversation context on subsequent messages.

Design rules:
  - Only SANITIZED user messages are ever stored (no raw PII).
  - Only SAFE assistant answers are stored (already passed the safety filter).
  - Sessions are bounded by MAX_HISTORY_TURNS to prevent token overflow.
  - No persistence: history lives in process memory (no DB required).
  - Thread-safe for async use (asyncio single-threaded event loop; no locks needed).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    """A single exchange: one user message + one assistant reply."""
    user: str       # sanitized user query
    assistant: str  # safe, filtered assistant answer


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

# session_id → bounded deque of turns
_sessions: dict[str, Deque[Turn]] = {}


def append_turn(session_id: str, user_msg: str, assistant_msg: str) -> None:
    """
    Record a completed turn.  Silently drops the oldest turn when
    the deque is at capacity (keeps memory bounded).
    """
    if not session_id:
        return
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=config.MAX_HISTORY_TURNS)
    _sessions[session_id].append(Turn(user=user_msg, assistant=assistant_msg))
    logger.debug(
        "Session %s: history now %d turn(s).",
        session_id,
        len(_sessions[session_id]),
    )


def get_history(session_id: str) -> list[Turn]:
    """
    Return all turns for a session (oldest first), or [] if unknown.
    Returns a plain list copy so callers can't mutate the deque.
    """
    if not session_id or session_id not in _sessions:
        return []
    return list(_sessions[session_id])


def clear_session(session_id: str) -> None:
    """Forget all history for a session (e.g. on explicit logout)."""
    _sessions.pop(session_id, None)
    logger.info("Session %s cleared.", session_id)


def history_as_messages(session_id: str) -> list[dict[str, str]]:
    """
    Return history formatted as an OpenAI-style messages list:
      [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

    This is directly usable in the Ollama /api/chat and Grok API payloads.
    """
    messages: list[dict[str, str]] = []
    for turn in get_history(session_id):
        messages.append({"role": "user", "content": turn.user})
        messages.append({"role": "assistant", "content": turn.assistant})
    return messages
