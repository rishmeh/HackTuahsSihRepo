"""
persona/tests/test_voice.py — Tests for mapping settings to Piper voice parameters.

Piper's length_scale controls pace: 1.0 is the model's natural speed, lower is
faster, higher is slower. Persona shows up in delivery as much as in words.

Run with: pytest persona/tests/test_voice.py -v
"""

import pytest

from learner.policy import default_settings
from persona.voice import DEFAULT_VOICE_MODEL, VoiceParams, voice_params


@pytest.fixture
def settings():
    return default_settings(age=12)


class TestShape:
    def test_returns_the_fields_piper_needs(self, settings):
        params = voice_params(settings)
        assert isinstance(params, VoiceParams)
        assert params.model.endswith(".onnx")
        assert 0.7 <= params.length_scale <= 1.3
        assert 0.0 <= params.noise_scale <= 1.0

    def test_defaults_to_the_bundled_voice(self, settings):
        assert voice_params(settings).model == DEFAULT_VOICE_MODEL


class TestPace:
    def test_playful_is_quicker_than_warm(self, settings):
        playful = voice_params(settings.model_copy(update={"encouragement_arm": "playful"}))
        warm = voice_params(settings.model_copy(update={"encouragement_arm": "warm"}))
        assert playful.length_scale < warm.length_scale

    def test_gentle_wrong_answer_handling_slows_down(self, settings):
        """A failure-sensitive child should never be corrected briskly."""
        gentle = voice_params(settings.model_copy(update={"wrong_answer_style": "gentle"}))
        analytical = voice_params(settings.model_copy(update={"wrong_answer_style": "analytical"}))
        assert gentle.length_scale > analytical.length_scale

    def test_terse_students_get_a_brisker_read(self, settings):
        terse = voice_params(settings.model_copy(update={"response_length": "terse"}))
        normal = voice_params(settings.model_copy(update={"response_length": "normal"}))
        assert terse.length_scale < normal.length_scale

    def test_pace_stays_within_intelligible_bounds_under_every_combination(self, settings):
        for arm in ("warm", "playful", "challenge", "plain"):
            for wrong in ("gentle", "supportive", "analytical"):
                for length in ("terse", "normal", "detailed"):
                    params = voice_params(settings.model_copy(update={
                        "encouragement_arm": arm, "wrong_answer_style": wrong, "response_length": length,
                    }))
                    assert 0.8 <= params.length_scale <= 1.25, (arm, wrong, length, params.length_scale)


class TestSynthesisKwargs:
    def test_exposes_kwargs_piper_synthesize_accepts(self, settings):
        kwargs = voice_params(settings).synthesis_kwargs()
        assert set(kwargs) == {"length_scale", "noise_scale", "noise_w"}
