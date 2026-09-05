"""
persona/tests/test_phrases.py — Tests for the code-owned phrase pools.

The SLM supplies content; these pools supply the vibe. They are what make the
personality consistent on a 0.6B model — and they are where the sarcasm rule
is enforced: a joke is only ever pointed at the situation, never at the child.

Run with: pytest persona/tests/test_phrases.py -v
"""

import random

import pytest

from persona.phrases import (
    ARMS,
    KINDS,
    SAFE_FOR_SARCASM,
    PhraseBook,
    Situation,
)


@pytest.fixture
def book():
    return PhraseBook(rng=random.Random(0))


class TestCoverage:
    """Every combination the decorator can ask for must have something to say."""

    def test_every_kind_has_phrases_for_every_arm(self, book):
        for kind in KINDS:
            for arm in ARMS:
                assert book.pick(kind, arm=arm, situation=Situation.QUESTION, sarcasm_allowed=False), (kind, arm)

    def test_every_wrong_answer_style_has_phrases(self, book):
        for style in ("gentle", "supportive", "analytical"):
            assert book.wrong_answer(style=style, sarcasm_allowed=False)

    def test_no_pool_is_a_single_phrase(self, book):
        """One phrase repeated every session is worse than none."""
        for kind in KINDS:
            for arm in ARMS:
                assert len(book.pool(kind, arm)) >= 3, (kind, arm)


class TestSarcasmRule:
    """Sarcasm fails closed: off by default, and never at the child's expense."""

    def test_sarcastic_phrases_are_never_returned_when_not_allowed(self, book):
        for _ in range(200):
            phrase = book.pick("encouragement", arm="playful", situation=Situation.REPEATED_QUESTION, sarcasm_allowed=False)
            assert not book.is_sarcastic(phrase)

    def test_sarcastic_phrases_can_appear_in_a_safe_situation_when_allowed(self, book):
        seen = {
            book.is_sarcastic(
                book.pick("encouragement", arm="playful", situation=Situation.REPEATED_QUESTION, sarcasm_allowed=True)
            )
            for _ in range(200)
        }
        assert True in seen

    def test_sarcasm_is_never_used_on_a_wrong_answer_even_when_allowed(self, book):
        """The rule that matters most."""
        for style in ("gentle", "supportive", "analytical"):
            for _ in range(200):
                assert not book.is_sarcastic(book.wrong_answer(style=style, sarcasm_allowed=True))

    def test_sarcasm_is_never_used_when_the_student_is_struggling(self, book):
        for _ in range(200):
            phrase = book.pick("encouragement", arm="playful", situation=Situation.STRUGGLING, sarcasm_allowed=True)
            assert not book.is_sarcastic(phrase)

    def test_the_unsafe_situations_are_exactly_the_ones_we_mean(self):
        assert Situation.WRONG_ANSWER not in SAFE_FOR_SARCASM
        assert Situation.STRUGGLING not in SAFE_FOR_SARCASM
        assert Situation.GREETING not in SAFE_FOR_SARCASM
        assert Situation.REPEATED_QUESTION in SAFE_FOR_SARCASM


class TestVariety:
    def test_does_not_repeat_the_same_phrase_back_to_back(self, book):
        previous = None
        for _ in range(50):
            phrase = book.pick("greeting", arm="warm", situation=Situation.GREETING, sarcasm_allowed=False)
            assert phrase != previous
            previous = phrase

    def test_uses_more_than_one_phrase_over_time(self, book):
        seen = {book.pick("celebration", arm="warm", situation=Situation.CORRECT_ANSWER, sarcasm_allowed=False) for _ in range(30)}
        assert len(seen) >= 3

    def test_is_deterministic_for_a_seeded_rng(self):
        a = PhraseBook(rng=random.Random(7))
        b = PhraseBook(rng=random.Random(7))
        picks = lambda bk: [bk.pick("greeting", arm="warm", situation=Situation.GREETING, sarcasm_allowed=False) for _ in range(10)]
        assert picks(a) == picks(b)


class TestArmCharacter:
    """The arms must actually sound different, or the bandit has nothing to learn."""

    def test_challenge_arm_dares_and_warm_arm_reassures(self, book):
        challenge = " ".join(book.pool("encouragement", "challenge")).lower()
        warm = " ".join(book.pool("encouragement", "warm")).lower()
        assert any(w in challenge for w in ("bet", "dare", "harder", "think you"))
        assert any(w in warm for w in ("got this", "okay", "with you", "take your time"))

    def test_plain_arm_has_no_exclamation_marks(self, book):
        """Plain means plain — for the student who asked Tot to get to the point."""
        for phrase in book.pool("encouragement", "plain"):
            assert "!" not in phrase


class TestSpecialLines:
    def test_listening_and_thinking_lines_exist_for_the_voice_agent(self, book):
        assert book.pick("listening", arm="warm", situation=Situation.LISTENING, sarcasm_allowed=False)
        assert book.pick("thinking", arm="warm", situation=Situation.THINKING, sarcasm_allowed=False)

    def test_error_line_never_blames_the_student(self, book):
        for phrase in book.pool("error", "warm"):
            assert "you" not in phrase.lower().split(" fault")[0] or "my" in phrase.lower()
