"""
quiz/models.py — Pydantic data models for the quiz generator.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# ---------------------------------------------------------------------------
# Quiz question
# ---------------------------------------------------------------------------

class QuizQuestion(BaseModel):
    id: int = Field(..., ge=1)
    type: QuestionType
    difficulty: Difficulty
    question: str = Field(..., min_length=5)
    options: Optional[list[str]] = Field(
        None,
        description="Required for multiple_choice questions (4 options)",
    )
    answer: str = Field(..., min_length=1)
    explanation: Optional[str] = None

    @model_validator(mode="after")
    def validate_options(self) -> "QuizQuestion":
        if self.type == QuestionType.MULTIPLE_CHOICE:
            if not self.options or len(self.options) < 2:
                raise ValueError("multiple_choice questions require at least 2 options.")
        return self


# ---------------------------------------------------------------------------
# Student info for quiz generation (input)
# ---------------------------------------------------------------------------

class QuizStudentProfile(BaseModel):
    age: int = Field(..., ge=4, le=18)
    grade: Optional[str] = None
    personality_traits: list[str] = Field(default_factory=list)
    covered_topics: list[str] = Field(
        ...,
        min_length=1,
        description="Topics the student has already studied",
    )


class QuizRequest(BaseModel):
    student: QuizStudentProfile
    subject: str = Field(..., min_length=2, max_length=100)
    num_questions: int = Field(default=7, ge=2, le=15)

    @field_validator("subject")
    @classmethod
    def strip_subject(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Full Quiz (output)
# ---------------------------------------------------------------------------

class Quiz(BaseModel):
    quiz_id: str = Field(default_factory=lambda: str(uuid4()))
    subject: str
    grade_level: Optional[str]
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    num_questions: int
    questions: list[QuizQuestion]

    @model_validator(mode="after")
    def validate_question_count(self) -> "Quiz":
        if len(self.questions) != self.num_questions:
            raise ValueError(
                f"Expected {self.num_questions} questions but got {len(self.questions)}."
            )
        return self
