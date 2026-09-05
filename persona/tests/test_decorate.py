"""
persona/tests/test_decorate.py — Tests for wrapping an SLM answer in Tot's voice.

The model produced the content. This adds the opener and closer that carry
the personality — chosen by the student's settings and the situation, and
skipped entirely for a student who asked Tot to get to the point.

Run with: pytest persona/tests/test_decorate.py -v
"""

import random

import pytest

from learner.policy import default_settings
from persona.decorate import decorate_answer
from persona.phrases import PhraseBook, Situation

ANSWER = "Plants make their food from sunlight, water and carbon dioxide."


@pytest.fixture
def book():
    return PhraseBook(rng=random.Random(0))


@pytest.fixture
def settings():
    return default_settings(age=12)


class TestBasics:
    def test_the_answer_itself_is_always_preserved(self, book, settings):
        for situation in Situation:
            assert ANSWER in decorate_answer(ANSWER, settings, situation, book)

    def test_a_question_gets_an_opener_or_a_closer(self, book, settings):
        decorated = decorate_answer(ANSWER, settings, Situation.QUESTION, book)
        assert decorated != ANSWER

    def test_an_empty_answer_is_returned_empty(self, book, settings):
        assert decorate_answer("", settings, Situation.QUESTION, book) == ""


class TestRespectsSettings:
    def test_terse_students_get_the_bare_answer(self, book, settings):
        """'Talk too much — just get to the point.' So: no decoration at all."""
        terse = settings.model_copy(update={"response_length": "terse"})
        assert decorate_answer(ANSWER, terse, Situation.QUESTION, book) == ANSWER

    def test_terse_students_still_get_a_gentle_line_on_a_wrong_answer(self, book, settings):
        """Brevity is a preference; kindness on failure is not optional."""
        terse = settings.model_copy(update={"response_length": "terse", "wrong_answer_style": "gentle"})
        decorated = decorate_answer(ANSWER, terse, Situation.WRONG_ANSWER, book)
        assert decorated != ANSWER

    def test_uses_the_students_encouragement_arm(self, book, settings):
        challenge = settings.model_copy(update={"encouragement_arm": "challenge"})
        warm = settings.model_copy(update={"encouragement_arm": "warm"})
        challenge_text = {decorate_answer(ANSWER, challenge, Situation.STRUGGLING, book) for _ in range(20)}
        warm_text = {decorate_answer(ANSWER, warm, Situation.STRUGGLING, book) for _ in range(20)}
        assert challenge_text.isdisjoint(warm_text)


class TestSituations:
    def test_wrong_answer_uses_the_wrong_answer_style(self, book, settings):
        gentle = settings.model_copy(update={"wrong_answer_style": "gentle"})
        analytical = settings.model_copy(update={"wrong_answer_style": "analytical"})
        g = {decorate_answer(ANSWER, gentle, Situation.WRONG_ANSWER, book) for _ in range(20)}
        a = {decorate_answer(ANSWER, analytical, Situation.WRONG_ANSWER, book) for _ in range(20)}
        assert g.isdisjoint(a)

    def test_correct_answer_gets_a_celebration(self, book, settings):
        decorated = decorate_answer(ANSWER, settings, Situation.CORRECT_ANSWER, book)
        opener = decorated.replace(ANSWER, "").strip()
        assert opener in book.pool("celebration", settings.encouragement_arm)


class TestSarcasm:
    def test_no_sarcasm_anywhere_when_the_gate_is_closed(self, book, settings):
        closed = settings.model_copy(update={"sarcasm_allowed": False})
        for situation in Situation:
            for _ in range(30):
                text = decorate_answer(ANSWER, closed, situation, book)
                for line in text.replace(ANSWER, "").strip().splitlines():
                    if line.strip():
                        assert not book.is_sarcastic(line.strip()), (situation, line)

    def test_never_sarcastic_on_a_wrong_answer_even_with_the_gate_open(self, book, settings):
        open_gate = settings.model_copy(update={"sarcasm_allowed": True})
        for _ in range(100):
            text = decorate_answer(ANSWER, open_gate, Situation.WRONG_ANSWER, book)
            for line in text.replace(ANSWER, "").strip().splitlines():
                if line.strip():
                    assert not book.is_sarcastic(line.strip())
