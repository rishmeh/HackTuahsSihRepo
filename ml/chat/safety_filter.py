"""
chat/safety_filter.py — Final output guardrail applied to ALL responses
before they are returned to the caller (regardless of source: SLM or Grok).

Checks:
  1. Length limit — truncates suspiciously long responses.
  2. Keyword blocklist — hard-blocks any output containing banned content.
  3. PII re-leakage check — catches if the model accidentally included PII.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard-block keyword / pattern list (child safety)
# ---------------------------------------------------------------------------

_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    # Violence
    re.compile(r"\b(kill|murder|shoot|stab|bomb|weapon|gun|knife|suicide|self[- ]harm)\b", re.I),
    # Adult / sexual
    re.compile(r"\b(sex|porn|nude|naked|adult\s+content|xxx)\b", re.I),
    # Hate speech
    re.compile(r"\b(racial slur|hate speech|n-word)\b", re.I),
    # Drug-related
    re.compile(r"\b(cocaine|heroin|meth|crystal\s+meth|drug\s+dealer)\b", re.I),
    # Prompt injection bleed-through
    re.compile(r"(ignore\s+previous|system\s+prompt|jailbreak)", re.I),
    # Explicit personal data patterns that should never appear in output
    re.compile(r"\b\d{10,}\b"),  # long digit strings (phone/ID)
    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),  # email
]

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class FilterResult:
    is_safe: bool
    text: str  # Cleaned / truncated text (only valid if is_safe=True)
    block_reason: str = ""


def apply_safety_filter(text: str) -> FilterResult:
    """
    Run all safety checks on *text*.

    Returns FilterResult with is_safe=True and the (possibly truncated) text,
    or is_safe=False with a block_reason if it fails any check.
    """
    # --- Check 1: Length limit ---
    if len(text) > config.MAX_RESPONSE_LENGTH:
        logger.warning(
            "Response truncated: length %d > max %d.", len(text), config.MAX_RESPONSE_LENGTH
        )
        text = text[: config.MAX_RESPONSE_LENGTH] + "…"

    # --- Check 2: Keyword blocklist ---
    for pattern in _BLOCKED_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(
                "Safety filter BLOCKED response. Pattern: %r matched %r",
                pattern.pattern,
                match.group(),
            )
            return FilterResult(
                is_safe=False,
                text="",
                block_reason=f"Blocked pattern: {match.group()!r}",
            )

    return FilterResult(is_safe=True, text=text)
