"""
chat/pipeline.py — Orchestrates the complete child-safe chat flow.

Flow:
  ChatRequest (query + student profile + session_id)
      │
      ▼
  [session_store.get_history]  ← load previous turns for this session
      │
      ▼
  [sanitizer]  ← strip PII from the raw query
      │
      ▼
  [slm_client] ← SLM gets: sanitized query + student profile + history (think=False)
      │
      ├─ SLM answered confidently?
      │       └─ [safety_filter]
      │               └─ safe? → [session_store.append_turn] → ChatResponse(source="slm")
      │
      └─ escalate=True / low confidence?
              ├─ [complexity_judge] ← hard gate (injection check etc.)
              │       └─ blocked? → ChatResponse(source="fallback")
              │
              └─ allowed escalation — branch on ESCALATION_MODE:
                      "model_thinking" → call_slm(..., think=True)
                                          └─ [safety_filter] → ChatResponse(source="slm_thinking", thinking=True)
                      "openrouter"     → call_openrouter(...)
                                          └─ [safety_filter] → ChatResponse(source="openrouter")

NOTE: session_store.append_turn is called only after a *successful* response
      so that fallback messages are never replayed as conversation history.
"""

from __future__ import annotations

import logging

import config
from chat.complexity_judge import evaluate_pre_slm, evaluate_post_slm
from chat.openrouter_client import call_openrouter
from chat.models import ChatRequest, ChatResponse, EscalationReason
from chat.safety_filter import apply_safety_filter
from chat.sanitizer import sanitize
from chat.session_store import append_turn, history_as_messages
from chat.slm_client import call_slm

logger = logging.getLogger(__name__)


async def run_chat_pipeline(request: ChatRequest) -> ChatResponse:
    """
    Execute the full child-safe chat pipeline and return a ChatResponse.

    All exceptions are caught internally; the caller always receives a
    well-formed response (possibly the configured fallback message).
    """

    # ------------------------------------------------------------------
    # Step 1: Load conversation history for this session
    # ------------------------------------------------------------------
    history = history_as_messages(request.session_id) if request.session_id else []
    if history:
        logger.info(
            "Session %s: injecting %d history message(s).",
            request.session_id,
            len(history),
        )

    # ------------------------------------------------------------------
    # Step 2: Sanitize the raw query — remove PII before any LLM sees it
    # ------------------------------------------------------------------
    sanitization = sanitize(request.query)
    sanitized_query = sanitization.sanitized_text

    if sanitization.pii_detected:
        logger.info(
            "PII removed from query. Entities: %s", sanitization.removed_entities
        )

    # ------------------------------------------------------------------
    # Step 3: Evaluate pre-SLM escalation (e.g. keywords, injection)
    # ------------------------------------------------------------------
    block_escalation, force_escalation, escalation_reason = evaluate_pre_slm(sanitized_query)

    slm_response = None
    if not force_escalation:
        # ------------------------------------------------------------------
        # Step 4: Call local SLM — fast path (think=False)
        # ------------------------------------------------------------------
        slm_response = await call_slm(sanitized_query, request.student, history, think=False)

        if slm_response is None:
            logger.error("SLM returned None. Using fallback response.")
            return ChatResponse(
                answer=config.FALLBACK_RESPONSE,
                source="fallback",
                escalated=False,
                escalation_reason=EscalationReason.SLM_ERROR,
                session_id=request.session_id,
            )

        # ------------------------------------------------------------------
        # Step 5: Evaluate post-SLM escalation
        # ------------------------------------------------------------------
        if not block_escalation:
            should_escalate, post_slm_reason = evaluate_post_slm(slm_response)
            if should_escalate:
                force_escalation = True
                escalation_reason = post_slm_reason

    if not force_escalation:
        # SLM answered confidently — run through safety filter
        assert slm_response is not None
        filter_result = apply_safety_filter(slm_response.answer)
        if filter_result.is_safe:
            if request.session_id:
                append_turn(request.session_id, sanitized_query, filter_result.text)
            return ChatResponse(
                answer=filter_result.text,
                source="slm",
                escalated=False,
                escalation_reason=EscalationReason.NONE,
                thinking=False,
                session_id=request.session_id,
            )
        else:
            logger.warning("SLM answer blocked by safety filter: %s", filter_result.block_reason)
            return ChatResponse(
                answer=config.FALLBACK_RESPONSE,
                source="fallback",
                escalated=False,
                escalation_reason=EscalationReason.NONE,
                session_id=request.session_id,
            )

    # ------------------------------------------------------------------
    # Step 6: Escalation — branch on ESCALATION_MODE
    # ------------------------------------------------------------------
    conf_log = slm_response.confidence if slm_response else 0.0
    logger.info(
        "Escalating. Mode=%s | Reason: %s | SLM confidence: %.2f",
        config.ESCALATION_MODE,
        escalation_reason,
        conf_log,
    )

    if config.ESCALATION_MODE == "model_thinking":
        return await _escalate_via_thinking(
            sanitized_query, request, history, escalation_reason, slm_response
        )
    else:
        return await _escalate_via_openrouter(
            sanitized_query, request, history, escalation_reason, slm_response
        )


async def _escalate_via_thinking(
    sanitized_query: str,
    request: ChatRequest,
    history: list[dict[str, str]],
    escalation_reason: EscalationReason,
    slm_response,
) -> ChatResponse:
    """Retry the local SLM with think=True for a higher-quality answer."""
    thinking_response = await call_slm(
        sanitized_query, request.student, history, think=True
    )

    if thinking_response is None:
        logger.error("Thinking-mode SLM returned None. Falling back.")
        fallback_text = (
            slm_response.answer if slm_response and slm_response.answer
            else config.FALLBACK_RESPONSE
        )
        filter_result = apply_safety_filter(fallback_text)
        return ChatResponse(
            answer=filter_result.text if filter_result.is_safe else config.FALLBACK_RESPONSE,
            source="fallback",
            escalated=True,
            escalation_reason=escalation_reason,
            thinking=True,
            session_id=request.session_id,
        )

    filter_result = apply_safety_filter(thinking_response.answer)
    if filter_result.is_safe:
        if request.session_id:
            append_turn(request.session_id, sanitized_query, filter_result.text)
        return ChatResponse(
            answer=filter_result.text,
            source="slm_thinking",
            escalated=True,
            escalation_reason=EscalationReason.THINKING_RETRY,
            thinking=True,
            session_id=request.session_id,
        )
    else:
        logger.warning("Thinking-mode answer blocked by safety filter: %s", filter_result.block_reason)
        return ChatResponse(
            answer=config.FALLBACK_RESPONSE,
            source="fallback",
            escalated=True,
            escalation_reason=escalation_reason,
            thinking=True,
            session_id=request.session_id,
        )


async def _escalate_via_openrouter(
    sanitized_query: str,
    request: ChatRequest,
    history: list[dict[str, str]],
    escalation_reason: EscalationReason,
    slm_response,
) -> ChatResponse:
    """Forward to OpenRouter — sends only sanitized query + sanitized history (no PII)."""
    openrouter_answer = await call_openrouter(sanitized_query, history)

    if openrouter_answer is None:
        logger.error("OpenRouter returned None. Falling back to SLM answer.")
        fallback_text = (
            slm_response.answer if slm_response and slm_response.answer
            else config.FALLBACK_RESPONSE
        )
        filter_result = apply_safety_filter(fallback_text)
        return ChatResponse(
            answer=filter_result.text if filter_result.is_safe else config.FALLBACK_RESPONSE,
            source="fallback",
            escalated=True,
            escalation_reason=escalation_reason,
            session_id=request.session_id,
        )

    filter_result = apply_safety_filter(openrouter_answer)
    if filter_result.is_safe:
        if request.session_id:
            append_turn(request.session_id, sanitized_query, filter_result.text)
        return ChatResponse(
            answer=filter_result.text,
            source="openrouter",
            escalated=True,
            escalation_reason=escalation_reason,
            session_id=request.session_id,
        )
    else:
        logger.warning("OpenRouter answer blocked by safety filter: %s", filter_result.block_reason)
        return ChatResponse(
            answer=config.FALLBACK_RESPONSE,
            source="fallback",
            escalated=True,
            escalation_reason=escalation_reason,
            session_id=request.session_id,
        )
