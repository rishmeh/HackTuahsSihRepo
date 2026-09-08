"""Tests for conversational persona setup and its voice trigger."""

from learner import config as learner_config
from learner.policy import derive_settings
from learner.profile_store import ProfileStore
from persona_setup import sessions
from voice_commands.intent import parse


def test_persona_setup_trigger_is_not_general_chat():
    assert parse("Help me set up my persona").name == "start_persona_setup"
    assert parse("customize my assistant personality").name == "start_persona_setup"
    assert parse("cancel persona setup").name == "cancel_persona_setup"


def test_setup_saves_a_profile_and_applies_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(learner_config, "LEARNER_DB_PATH", tmp_path / "learner.db")
    profile_id = "laptop-user"
    sessions.cancel(profile_id)

    first = sessions.start(profile_id, age=14)
    assert "Question one" in first

    answers = [
        "forest",      # Q1: explore
        "hint",        # Q2: help_seeking
        "figure",      # Q3: trial
        "story",       # Q4: narrative
        "raise",       # Q5: confidence
        "curious",     # Q6: failure_sensitivity
        "stories",     # Q7: narrative
        "together",    # Q8: peer
        "master",      # Q9: mastery
        "explanation"  # Q10: explain_why -> detailed length
    ]
    replies = []
    for index, answer in enumerate(answers):
        accepted, reply, complete = sessions.answer(profile_id, answer, age=14)
        replies.append(reply)
        assert accepted
        assert complete is (index == len(answers) - 1)

    assert "saved your persona" in replies[-1].lower()
    assert not sessions.is_active(profile_id)

    stored = ProfileStore(learner_config.LEARNER_DB_PATH).get(profile_id)
    assert stored is not None
    settings = derive_settings(stored.profile)
    assert settings.response_format == "narrative"
    assert settings.response_length == "detailed"
    assert settings.persona_mode == "peer"
    assert settings.task_framing == "mastery"


def test_setup_skip_uses_safe_default_and_can_be_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr(learner_config, "LEARNER_DB_PATH", tmp_path / "learner.db")
    profile_id = "temporary-user"
    sessions.cancel(profile_id)

    sessions.start(profile_id, age=10)
    accepted, reply, complete = sessions.answer(profile_id, "skip", age=10)
    assert accepted and not complete
    assert "Question two" in reply
    assert sessions.cancel(profile_id)
    assert not sessions.is_active(profile_id)
    assert ProfileStore(learner_config.LEARNER_DB_PATH).get(profile_id) is None
