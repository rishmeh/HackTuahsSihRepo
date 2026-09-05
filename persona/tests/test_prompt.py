"""
persona/tests/test_prompt.py — Tests for the persona block injected into the SLM prompt.

The persona wraps the existing system prompt; it must never weaken it. The
JSON contract, the escalation rules and the child-safety rules stay exactly
as they were, and they keep the last word.

Run with: pytest persona/tests/test_prompt.py -v
"""

import pytest

from learner.policy import default_settings
from persona.prompt import build_persona_block, compose_system_prompt

BASE_PROMPT = """\
You are KidBot, a friendly, respectful, and safe educational assistant
for children.

STRICT RULES YOU MUST FOLLOW:
1. Always respond in simple, clear language.
5. You MUST respond ONLY with a valid JSON object.

JSON SCHEMA (respond exactly like this):
{
  "answer": "<your child-safe answer here>",
  "escalate": <true|false>
}
"""


@pytest.fixture
def settings():
    return default_settings(age=12)


class TestPersonaBlock:
    def test_names_tot_not_kidbot(self, settings):
        block = build_persona_block(settings)
        assert "Tot" in block
        assert "KidBot" not in block

    def test_includes_every_prompt_directive_from_the_settings(self, settings):
        block = build_persona_block(settings)
        for directive in settings.prompt_directives:
            assert directive in block

    def test_includes_no_more_directives_than_the_settings_carry(self, settings):
        """The 0.6B model gets three style lines. The block must not smuggle in more."""
        block = build_persona_block(settings)
        directive_lines = [l for l in block.splitlines() if l.strip().startswith("- ")]
        assert len(directive_lines) <= len(settings.prompt_directives) + 1  # +1 for the persona-mode line

    def test_reflects_the_persona_mode(self, settings):
        teacher = build_persona_block(settings.model_copy(update={"persona_mode": "teacher"}))
        peer = build_persona_block(settings.model_copy(update={"persona_mode": "peer"}))
        assert teacher != peer

    def test_never_mentions_sarcasm_to_the_model(self, settings):
        """
        Sarcasm is delivered by the code-owned phrase pools, not by the model.
        Asking a 0.6B model to 'be sarcastic' is how a child gets mocked.
        """
        allowed = build_persona_block(settings.model_copy(update={"sarcasm_allowed": True}))
        assert "sarcas" not in allowed.lower()
        assert "ironic" not in allowed.lower()


class TestComposition:
    def test_composed_prompt_contains_the_block(self, settings):
        composed = compose_system_prompt(BASE_PROMPT, build_persona_block(settings))
        assert "Tot" in composed

    def test_strict_rules_and_json_schema_survive_untouched(self, settings):
        composed = compose_system_prompt(BASE_PROMPT, build_persona_block(settings))
        assert "STRICT RULES YOU MUST FOLLOW:" in composed
        assert '"escalate": <true|false>' in composed
        assert "respond ONLY with a valid JSON object" in composed

    def test_rules_come_after_the_persona_so_they_have_the_last_word(self, settings):
        composed = compose_system_prompt(BASE_PROMPT, build_persona_block(settings))
        assert composed.index("Tot") < composed.index("STRICT RULES")

    def test_replaces_the_kidbot_identity_line(self, settings):
        composed = compose_system_prompt(BASE_PROMPT, build_persona_block(settings))
        assert "You are KidBot" not in composed

    def test_refuses_a_base_prompt_without_the_safety_rules(self, settings):
        """Composing onto the wrong prompt must fail loudly, not silently drop safety."""
        with pytest.raises(ValueError, match="STRICT RULES"):
            compose_system_prompt("You are a bot.", build_persona_block(settings))
