"""
persona/prompt.py — The persona block injected into the SLM system prompt.

The block replaces only the identity preamble of the existing chat prompt.
The STRICT RULES, the escalation policy and the JSON schema that follow it
are untouched and come *after* the persona, so they keep the last word.

What the model is told is deliberately small: who it is, how this student
likes to be talked to (one line), and at most three style directives from
TotSettings. It is never told to be sarcastic — that tone is delivered by the
code-owned phrase pools, where it can be gated.
"""

from __future__ import annotations

from learner.models import TotSettings
from persona import config

# The marker in the base prompt where the rules begin. Everything before it
# is identity, which the persona replaces; everything from it on is kept.
RULES_MARKER = "STRICT RULES"

_MODE_LINES = {
    "teacher": "Guide the student clearly, one step at a time.",
    "peer": "Work it out alongside the student, the way a friend would.",
    "socratic": "Prefer asking one guiding question over giving the whole answer.",
    "independent": "Be brief and stay out of the way unless asked.",
}


def build_persona_block(settings: TotSettings, name: str | None = None) -> str:
    """Identity plus the few style directives the model can actually follow."""
    name = name or config.PERSONA_NAME
    mode_line = _MODE_LINES.get(settings.persona_mode, _MODE_LINES["teacher"])

    lines = [
        f"You are {name}, a friendly, respectful and safe study companion for",
        "children, who lives on the student's desk and helps them learn.",
        "",
        "How to talk to this student:",
        f"- {mode_line}",
        *[f"- {directive}" for directive in settings.prompt_directives],
        "",
    ]
    return "\n".join(lines)


def compose_system_prompt(base_prompt: str, persona_block: str) -> str:
    """
    Put the persona in front of the existing rules.

    Raises:
        ValueError: If the base prompt has no STRICT RULES section. Composing
            onto the wrong prompt must fail loudly rather than silently drop
            the child-safety rules.
    """
    index = base_prompt.find(RULES_MARKER)
    if index == -1:
        raise ValueError(
            f"base prompt has no {RULES_MARKER!r} section; refusing to compose a "
            "persona onto a prompt without the safety rules"
        )
    return persona_block.rstrip("\n") + "\n\n" + base_prompt[index:]
