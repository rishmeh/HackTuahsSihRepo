"""
notes/indexer.py — Builds and maintains the keyword→note concept map.

When a note is created or updated, extract_and_index() is called.
It sends a single fast SLM call to extract concepts/keywords from the
note text, then stores them in the note_index table.

Schema:
  note_index
    id          INTEGER PK
    note_id     INTEGER  FK → notes.id
    profile_id  INTEGER
    keyword     TEXT     (lowercase, e.g. "addition", "photosynthesis")
    concept     TEXT     (one-sentence principle, e.g. "adding two numbers gives their sum")
    snippet     TEXT     (the original chunk of note text that gave rise to this concept)
    created_at  INTEGER  (ms epoch)

Keyword matching at query time uses SQLite FTS5 on the keyword + concept
columns so "how do I combine numbers?" can still match "addition".
"""

from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
import httpx

import config

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"

# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_CREATE_INDEX_TABLE = """
CREATE TABLE IF NOT EXISTS note_index (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id    INTEGER NOT NULL,
    profile_id INTEGER NOT NULL DEFAULT 0,
    keyword    TEXT    NOT NULL,
    concept    TEXT    NOT NULL DEFAULT '',
    snippet    TEXT    NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
)
"""

_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS note_index_fts
USING fts5(
    keyword,
    concept,
    content='note_index',
    content_rowid='id'
)
"""

_FTS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS note_index_fts_insert
AFTER INSERT ON note_index BEGIN
    INSERT INTO note_index_fts(rowid, keyword, concept)
    VALUES (new.id, new.keyword, new.concept);
END
"""

_FTS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS note_index_fts_delete
AFTER DELETE ON note_index BEGIN
    INSERT INTO note_index_fts(note_index_fts, rowid, keyword, concept)
    VALUES ('delete', old.id, old.keyword, old.concept);
END
"""


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(_CREATE_INDEX_TABLE)
    await db.execute(_CREATE_FTS)
    await db.execute(_FTS_INSERT_TRIGGER)
    await db.execute(_FTS_DELETE_TRIGGER)
    await db.commit()


# ---------------------------------------------------------------------------
# SLM concept extraction
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = textwrap.dedent("""\
    You are a concept extractor for a student study tool.
    Given a piece of study-note text, identify the key educational concepts it covers.

    RULES:
    1. Return ONLY a valid JSON array — no extra text, no markdown.
    2. Each element is an object with exactly two fields:
       "keyword"  — a single lowercase word or short phrase (e.g. "addition", "photosynthesis")
       "concept"  — one sentence describing the principle (e.g. "adding two numbers gives their sum")
    3. Extract between 1 and 8 concepts per note. Prefer quality over quantity.
    4. Keywords must be general enough to match related questions
       (e.g. keyword "addition" covers "5+5", not just "7+3").

    Example output:
    [
      {"keyword": "addition", "concept": "adding two numbers together gives their combined sum"},
      {"keyword": "subtraction", "concept": "taking one number away from another gives the difference"}
    ]
""")

_EXTRACT_USER = "Extract concepts from this study note:\n\n{text}"


async def _call_slm_extract(text: str) -> list[dict]:
    """Call local Ollama to extract keywords/concepts from note text.
    Returns a list of {keyword, concept} dicts, or [] on failure."""
    # Truncate very long notes to keep the extraction call fast
    truncated = text[:3000] if len(text) > 3000 else text

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": _EXTRACT_USER.format(text=truncated)},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 512},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{config.OLLAMA_BASE_URL}/api/chat", json=payload)
            r.raise_for_status()
            raw: str = r.json()["message"]["content"]

        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(l for l in lines if not l.startswith("```")).strip()

        data = json.loads(raw)
        # Unwrap {"concepts": [...]} if the model wraps it
        if isinstance(data, dict):
            for key in ("concepts", "keywords", "items", "results"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                logger.warning("Concept extractor returned unexpected dict: %r", raw[:200])
                return []

        if not isinstance(data, list):
            logger.warning("Concept extractor returned non-list: %r", raw[:200])
            return []

        valid = []
        for item in data:
            if isinstance(item, dict) and "keyword" in item and "concept" in item:
                valid.append({
                    "keyword": str(item["keyword"]).lower().strip(),
                    "concept": str(item["concept"]).strip(),
                })
        return valid

    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("Concept extraction SLM call failed: %s", exc)
        return []
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Concept extraction parse error: %s", exc)
        return []
    except Exception as exc:
        logger.exception("Unexpected error in concept extraction: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_and_index(note_id: int, profile_id: int, content: str, title: str = "") -> int:
    """
    Extract concepts from a note and store them in note_index.
    Deletes any existing index entries for this note first (idempotent on re-index).

    Returns the number of concepts indexed.
    """
    if not content or not content.strip():
        logger.info("Note %d has no content — skipping indexing.", note_id)
        return 0

    # Prepend the title for better concept extraction context
    full_text = f"{title}\n\n{content}".strip() if title else content

    concepts = await _call_slm_extract(full_text)
    if not concepts:
        logger.warning("No concepts extracted for note %d.", note_id)
        return 0

    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)

        # Remove stale index entries for this note
        await db.execute("DELETE FROM note_index WHERE note_id = ?", (note_id,))

        for item in concepts:
            await db.execute(
                "INSERT INTO note_index (note_id, profile_id, keyword, concept, snippet, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    profile_id,
                    item["keyword"],
                    item["concept"],
                    full_text[:500],   # store a short snippet for context retrieval
                    now,
                ),
            )

        await db.commit()

    logger.info(
        "Indexed %d concept(s) for note %d (profile %d): %s",
        len(concepts),
        note_id,
        profile_id,
        [c["keyword"] for c in concepts],
    )
    return len(concepts)


async def delete_index_for_note(note_id: int) -> None:
    """Remove all index entries when a note is deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        await db.execute("DELETE FROM note_index WHERE note_id = ?", (note_id,))
        await db.commit()
    logger.info("Removed index entries for deleted note %d.", note_id)
