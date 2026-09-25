"""
flashcards/generator.py - Generates a FlashcardDeck using the local Ollama SLM.

Uses the fast path (think=False) - flashcard generation does not require
deep reasoning or escalation to OpenRouter.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

import config
from flashcards.models import Flashcard, FlashcardDeck, FlashcardRequest
from flashcards.template import SYSTEM_PROMPT, build_user_prompt, format_deck

logger = logging.getLogger(__name__)


def _parse_cards(raw: str, expected_count: int, default_topic: str = "general") -> Optional[list[Flashcard]]:
    """
    Parse the SLM raw output into a list of Flashcard objects.
    Strips optional markdown fences before attempting JSON parse.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()

    try:
        data = json.loads(text)
    except Exception as exc:
        logger.warning("Flashcard JSON parse error: %s | raw=%r", exc, raw[:200])
        return None

    raw_list: list = []
    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict):
        if "front" in data or "question" in data:
            raw_list = [data]
        else:
            for key in ("cards", "flashcards", "data", "items", "results", "deck"):
                if key in data and isinstance(data[key], list):
                    raw_list = data[key]
                    break
            else:
                logger.warning("Flashcard SLM returned non-list JSON: %r", text[:200])
                return None
    else:
        return None

    cards: list[Flashcard] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        # Normalize field names from various SLM styles
        if "front" not in item and "question" in item:
            item["front"] = item["question"]
        if "back" not in item and "answer" in item:
            item["back"] = item["answer"]
        if "topic" not in item or not item["topic"]:
            item["topic"] = default_topic

        try:
            cards.append(Flashcard(**item))
        except Exception as e:
            logger.warning("Skipping malformed flashcard: %s | item=%r", e, item)

    if not cards:
        logger.warning("No valid flashcards parsed from SLM response.")
        return None

    return cards


async def generate_flashcard_deck(req: FlashcardRequest) -> FlashcardDeck:
    """
    Generate a validated FlashcardDeck for the given request using the local SLM.

    Raises:
        RuntimeError: If the SLM is unreachable or returns unparseable output.
    """
    logger.info(
        "Generating %d flashcard(s) | subject=%r | topics=%s",
        req.num_cards, req.subject, req.student.covered_topics,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(req)},
    ]

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": config.SLM_KEEP_ALIVE,
        "format": "json",
        "options": {
            "temperature": 0.5,
            "num_predict": 2000,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=config.OLLAMA_TIMEOUT * 2) as client:
            response = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            raw_content: str = response.json()["message"]["content"]
    except httpx.ConnectError:
        raise RuntimeError(f"Cannot connect to Ollama at {config.OLLAMA_BASE_URL}.")
    except httpx.TimeoutException:
        raise RuntimeError(f"Ollama request timed out after {config.OLLAMA_TIMEOUT * 2}s.")
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Ollama HTTP error: {exc}")

    cards = _parse_cards(raw_content, req.num_cards, default_topic=req.subject)
    if cards is None:
        raise RuntimeError(
            "Flashcard generation failed - SLM returned unparseable output. "
            "Check Ollama logs or try a simpler subject/topics list."
        )

    deck = FlashcardDeck(
        subject=req.subject,
        grade_level=req.student.grade,
        num_cards=len(cards),
        cards=cards,
    )
    logger.info("Flashcard deck generated: %s (%d cards)", deck.deck_id, deck.num_cards)
    return deck


async def generate_and_format_deck(req: FlashcardRequest) -> tuple[FlashcardDeck, str]:
    """Convenience wrapper returning both the deck object and formatted text."""
    deck = await generate_flashcard_deck(req)
    return deck, format_deck(deck)
