"""
chat/complexity_judge.py — Hard gate that decides whether to allow
escalation from the SLM to the Grok API.

This module is a separate layer of defence: even if the SLM says
"escalate: true", we run additional checks to make sure:
  1. The query is genuinely complex (not a prompt-injection attempt).
  2. The sanitized query does not contain forbidden patterns.
  3. Confidence is below the configured threshold.

If any check fails the escalation is blocked and a safe fallback is used.
"""

from __future__ import annotations

import logging
import re

import config
from chat.models import EscalationReason, SLMResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns that should NEVER be escalated (injection / abuse attempts)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+.{0,40}(DAN|jailbreak)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?instructions", re.IGNORECASE),
    re.compile(r"</?(?:script|iframe|object|embed|form)\b", re.IGNORECASE),
    re.compile(r"\bsudo\b|\broot\b|\badmin\b|\bpassword\b|\bapi[_\s-]?key\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Patterns that should ALWAYS be escalated (advanced / complex topics)
# ---------------------------------------------------------------------------
_COMPLEXITY_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"\b(quantum|encryption|cryptography|algorithm|architecture|calculus|thermodynamics)\b", re.IGNORECASE),
    re.compile(r"\b(relativity|neural network|machine learning|artificial intelligence)\b", re.IGNORECASE),
    re.compile(r"\b(design a|build a|code a|write a program)\b", re.IGNORECASE),
    re.compile(r"\b(political|historical context|philosophical|existential)\b", re.IGNORECASE),
    re.compile(r"\b(matrix|eigenvalue|jacobian|lyapunov|asymptotically|dynamical system|differential equation|mathematics|prove that|rigorous bound)\b", re.IGNORECASE),
]

# Minimum query length to justify escalation (very short queries should not escalate)
_MIN_ESCALATION_QUERY_LENGTH: int = 10


def evaluate_pre_slm(sanitized_query: str) -> tuple[bool, bool, EscalationReason]:
    """
    Pre-SLM evaluation.
    Returns (block_escalation, force_escalation, reason).
    """
    # Guard: query too short
    if len(sanitized_query.strip()) < _MIN_ESCALATION_QUERY_LENGTH:
        logger.info("Escalation blocked: query too short.")
        return True, False, EscalationReason.NONE

    # Guard: injection attempt detection
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(sanitized_query):
            logger.warning("Escalation blocked: potential injection detected. Pattern: %s", pattern.pattern)
            return True, False, EscalationReason.NONE

    # Auto-escalate highly complex keywords
    for pattern in _COMPLEXITY_KEYWORDS:
        if pattern.search(sanitized_query):
            logger.info("Escalation forced by complexity keyword match. Pattern: %s", pattern.pattern)
            return False, True, EscalationReason.COMPLEXITY

    return False, False, EscalationReason.NONE


def evaluate_post_slm(slm_response: SLMResponse) -> tuple[bool, EscalationReason]:
    """
    Post-SLM evaluation if pre-SLM didn't force an escalation.
    Returns (should_escalate, reason).
    """
    if slm_response.escalate:
        logger.info("SLM requested escalation. Reason: %s", slm_response.reason or "none given")
        return True, EscalationReason.COMPLEXITY

    if slm_response.confidence < config.ESCALATION_CONFIDENCE_THRESHOLD:
        logger.info(
            "Escalation triggered by low confidence: %.2f < %.2f",
            slm_response.confidence,
            config.ESCALATION_CONFIDENCE_THRESHOLD,
        )
        return True, EscalationReason.LOW_CONFIDENCE

    return False, EscalationReason.NONE
