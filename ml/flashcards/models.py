"""
flashcards/models.py - Pydantic data models for the flashcard generator.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Flashcard(BaseModel):
    """A single study flashcard with a front (question/prompt) and back (answer)."""

    front: str = Field(..., min_length=3, description="Question or prompt on the card")
    back: str = Field(..., min_length=1, description="Answer or explanation on the card")
    topic: str = Field(..., description="The topic this card belongs to")
    difficulty: Difficulty = Difficulty.MEDIUM


class FlashcardDeck(BaseModel):
    """A generated set of flashcards for a student."""

    deck_id: str = Field(default_factory=lambda: str(uuid4()))
    subject: str
    grade_level: Optional[str] = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    num_cards: int
    cards: list[Flashcard]


class FlashcardStudentProfile(BaseModel):
    age: int = Field(..., ge=4, le=18)
    grade: Optional[str] = None
    covered_topics: list[str] = Field(
        ...,
        min_length=1,
        description="Topics the student has studied - cards are generated from these",
    )


class FlashcardRequest(BaseModel):
    student: FlashcardStudentProfile
    subject: str = Field(..., min_length=2, max_length=100)
    num_cards: int = Field(default=10, ge=5, le=20)

    @field_validator("subject")
    @classmethod
    def strip_subject(cls, v: str) -> str:
        return v.strip()