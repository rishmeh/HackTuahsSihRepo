"""
flashcards/template.py - System prompt and formatter for flashcard generation.
"""

from __future__ import annotations

import textwrap

from flashcards.models import FlashcardDeck, FlashcardRequest

# ---------------------------------------------------------------------------
# System prompt - instructs the model to emit a JSON array of flashcards
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
    You are KidBot, an educational assistant that creates study flashcards for children.
    Generate concise, age-appropriate flashcards to help a student review what they studied.

    STRICT RULES:
    1. Each card must have a clear front (question or prompt) and back (answer/explanation).
    2. Use simple, encouraging language suited to the student's age.
    3. Never produce any content that is violent, sexual, hateful, or inappropriate.
    4. You MUST respond ONLY with a valid JSON object — no extra text, no markdown fences.

    JSON SCHEMA (output this exact structure):
    {
      "cards": [
        {
          "front": "<question or prompt>",
          "back": "<answer or explanation>",
          "topic": "<topic name>",
          "difficulty": "easy"
        }
      ]
    }
""")


def build_user_prompt(req: FlashcardRequest) -> str:
    """Build the user-facing prompt describing what flashcards to generate."""
    topics = ", ".join(req.student.covered_topics)
    return textwrap.dedent(f"""\
        STUDENT CONTEXT:
        - Age: {req.student.age} years old
        - Grade: {req.student.grade or "unknown"}
        - Subject: {req.subject}
        - Topics studied: {topics}

        Generate exactly {req.num_cards} flashcards covering the topics above.
        Keep answers short and easy to understand.
        Respond ONLY with the raw JSON object.
    """)


def format_deck(deck: FlashcardDeck) -> str:
    """Return a human-readable text version of the flashcard deck."""
    lines = [
        f"Flashcard Deck: {deck.subject}",
        f"Generated: {deck.generated_at}",
        f"Cards: {deck.num_cards}",
        "-" * 40,
    ]
    for i, card in enumerate(deck.cards, 1):
        lines.append(f"\n[{i}] ({card.difficulty.upper()}) - {card.topic}")
        lines.append(f"  Q: {card.front}")
        lines.append(f"  A: {card.back}")
    return "\n".join(lines)
