"""
chat/models.py — Pydantic data models for the chat pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class EscalationReason(str, Enum):
    COMPLEXITY = "complexity"
    LOW_CONFIDENCE = "low_confidence"
    THINKING_RETRY = "thinking_retry"   # local model re-run with think=True
    SLM_ERROR = "slm_error"
    NONE = "none"


# ---------------------------------------------------------------------------
# Inbound
# ---------------------------------------------------------------------------

class StudentProfile(BaseModel):
    """Rich context given to the SLM only — NEVER forwarded to Grok."""

    name: Optional[str] = Field(None, description="Student's first name (SLM use only)")
    age: int = Field(..., ge=4, le=18, description="Student age in years")
    grade: Optional[str] = Field(None, description="e.g. '5th grade'")
    personality_traits: list[str] = Field(
        default_factory=list,
        description="e.g. ['curious', 'visual learner', 'shy']",
    )
    interests: list[str] = Field(
        default_factory=list,
        description="e.g. ['dinosaurs', 'football']",
    )
    language_level: Optional[str] = Field(
        None,
        description="'beginner' | 'intermediate' | 'advanced'",
    )


class ChatRequest(BaseModel):
    """Full incoming chat request from the application layer."""

    query: str = Field(..., min_length=1, max_length=2000)
    student: StudentProfile
    session_id: Optional[str] = Field(None, description="Optional session identifier")

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Internal SLM response (parsed from SLM JSON output)
# ---------------------------------------------------------------------------

class SLMResponse(BaseModel):
    """Structured response that the SLM must return as JSON."""

    answer: str = Field(..., description="SLM's answer to the child-safe query")
    escalate: bool = Field(
        False,
        description="True if the query is too complex for the SLM",
    )
    confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="SLM's self-rated confidence (0-1)",
    )
    reason: Optional[str] = Field(
        None,
        description="Optional explanation of why escalation is needed",
    )


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    """Final response returned to the caller."""

    answer: str
    source: str = Field(
        description="'slm' | 'slm_thinking' | 'openrouter' | 'slm_vision' | 'fallback'",
    )
    escalated: bool = False
    escalation_reason: EscalationReason = EscalationReason.NONE
    thinking: bool = Field(
        False,
        description="True when the answer was produced via a thinking-mode retry",
    )
    session_id: Optional[str] = None
