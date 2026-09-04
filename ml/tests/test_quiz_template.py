"""
tests/test_quiz_template.py — Unit tests for quiz parsing and validation.

Run with: pytest tests/test_quiz_template.py -v
"""

import json
import pytest
from quiz.models import QuizStudentProfile
from quiz.template import parse_quiz_from_json, format_quiz


def _make_student() -> QuizStudentProfile:
    return QuizStudentProfile(
        age=10,
        grade="5th",
        personality_traits=["curious"],
        covered_topics=["fractions", "geometry"],
    )


def _make_questions(n: int) -> list[dict]:
    questions = []
    for i in range(1, n + 1):
        questions.append(
            {
                "id": i,
                "type": "multiple_choice",
                "difficulty": "easy",
                "question": f"What is {i} + {i}?",
                "options": [str(i * 2), str(i + 1), str(i + 3), str(i + 5)],
                "answer": str(i * 2),
                "explanation": f"{i} + {i} = {i * 2}",
            }
        )
    return questions


class TestQuizParsing:
    def test_valid_7_questions(self):
        raw = json.dumps({"questions": _make_questions(7)})
        quiz = parse_quiz_from_json(raw, 7, _make_student(), "Mathematics")
        assert quiz is not None
        assert quiz.num_questions == 7
        assert len(quiz.questions) == 7

    def test_valid_5_questions(self):
        raw = json.dumps({"questions": _make_questions(5)})
        quiz = parse_quiz_from_json(raw, 5, _make_student(), "Science")
        assert quiz is not None
        assert len(quiz.questions) == 5

    def test_too_few_questions_returns_none(self):
        raw = json.dumps({"questions": _make_questions(3)})
        quiz = parse_quiz_from_json(raw, 5, _make_student(), "History")
        assert quiz is None

    def test_more_than_10_capped_at_10(self):
        raw = json.dumps({"questions": _make_questions(12)})
        quiz = parse_quiz_from_json(raw, 10, _make_student(), "Science")
        assert quiz is not None
        assert quiz.num_questions <= 10

    def test_malformed_json_returns_none(self):
        quiz = parse_quiz_from_json("this is not json", 5, _make_student(), "Math")
        assert quiz is None

    def test_list_format_accepted(self):
        """SLM may return a bare list instead of {"questions": [...]}"""
        raw = json.dumps(_make_questions(6))
        quiz = parse_quiz_from_json(raw, 6, _make_student(), "Geography")
        assert quiz is not None
        assert len(quiz.questions) == 6

    def test_questions_renumbered_sequentially(self):
        questions = _make_questions(5)
        # Mess up IDs
        for i, q in enumerate(questions):
            q["id"] = i * 100
        raw = json.dumps({"questions": questions})
        quiz = parse_quiz_from_json(raw, 5, _make_student(), "Math")
        assert quiz is not None
        ids = [q.id for q in quiz.questions]
        assert ids == list(range(1, 6))

    def test_true_false_question(self):
        questions = [
            {
                "id": i,
                "type": "true_false" if i == 1 else "multiple_choice",
                "difficulty": "easy",
                "question": "Is the Earth round?",
                "options": None if i == 1 else ["A", "B", "C", "D"],
                "answer": "True" if i == 1 else "A",
            }
            for i in range(1, 6)
        ]
        raw = json.dumps({"questions": questions})
        quiz = parse_quiz_from_json(raw, 5, _make_student(), "Science")
        assert quiz is not None


class TestQuizFormatting:
    def test_format_output_contains_subject(self):
        raw = json.dumps({"questions": _make_questions(5)})
        quiz = parse_quiz_from_json(raw, 5, _make_student(), "Mathematics")
        assert quiz is not None
        text = format_quiz(quiz)
        assert "MATHEMATICS" in text
        assert "Q1." in text
        assert "Q5." in text

    def test_format_includes_answers(self):
        raw = json.dumps({"questions": _make_questions(5)})
        quiz = parse_quiz_from_json(raw, 5, _make_student(), "Mathematics")
        text = format_quiz(quiz)
        assert "✓ Answer:" in text
