"""
notes/note_store.py — Query the note index to find notes relevant to a question.

This is the retrieval half of the pipeline. Given a student query:
  1. Run FTS5 full-text search on keyword + concept columns.
  2. Fall back to LIKE search if FTS returns nothing.
  3. Fetch the full note content for matched note IDs.
  4. Return a NoteContext object the chat pipeline can inject into the SLM prompt.

No embeddings, no external dependencies — pure SQLite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"

# Maximum number of distinct notes to include as context
_MAX_NOTES = 3
# Maximum characters of note content to pass as context (keeps prompt manageable)
_MAX_CONTENT_CHARS = 1200


@dataclass
class NoteContext:
    """Relevant note excerpts found for a query, ready to inject into a prompt."""

    found: bool                        # True if at least one note matched
    matched_keywords: list[str]        # The concept keywords that matched
    concepts: list[str]                # One-sentence concept descriptions
    note_snippets: list[str]           # Truncated note content chunks
    note_titles: list[str]             # Titles for attribution in the prompt

    def as_prompt_block(self) -> str:
        """
        Format the context as a structured block to prepend to the SLM prompt.
        Returns an empty string when found=False.
        """
        if not self.found:
            return ""

        lines = ["[STUDENT'S NOTES — use these as the primary source for your answer]"]
        for i, (title, snippet, concept) in enumerate(
            zip(self.note_titles, self.note_snippets, self.concepts), start=1
        ):
            lines.append(f"\nNote {i}: {title}")
            lines.append(f"Concept: {concept}")
            lines.append(f"Content:\n{snippet}")
        lines.append("\n[END OF STUDENT'S NOTES]")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenise_query(query: str) -> list[str]:
    """
    Break a query into searchable tokens.
    Strips punctuation and short stop-words, returns lowercase tokens.
    """
    import re
    stop = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "on", "at", "by", "for", "with", "about",
        "against", "between", "through", "during", "before", "after", "above",
        "below", "from", "up", "down", "out", "off", "over", "under", "again",
        "further", "then", "once", "what", "how", "why", "when", "where",
        "who", "which", "that", "this", "these", "those", "i", "me", "my",
        "we", "our", "you", "your", "he", "she", "it", "they", "them",
        "and", "or", "but", "if", "so", "yet", "nor",
    }
    tokens = re.findall(r"[a-z]+", query.lower())
    return [t for t in tokens if t not in stop and len(t) > 2]


def _build_fts_query(tokens: list[str]) -> str:
    """Build an FTS5 OR query from tokens."""
    return " OR ".join(tokens)


async def _fetch_note_content(db: aiosqlite.Connection, note_ids: list[int]) -> dict[int, tuple[str, str]]:
    """Return {note_id: (title, content)} for the given IDs."""
    if not note_ids:
        return {}
    placeholders = ",".join("?" * len(note_ids))
    db.row_factory = aiosqlite.Row
    rows = await (
        await db.execute(
            f"SELECT id, title, content FROM notes WHERE id IN ({placeholders})",
            note_ids,
        )
    ).fetchall()
    return {row["id"]: (row["title"] or "Untitled", row["content"] or "") for row in rows}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def find_relevant_notes(query: str, profile_id: int) -> NoteContext:
    """
    Search the note index for concepts relevant to the student's query.

    Strategy:
      1. FTS5 search on keyword + concept columns
      2. LIKE fallback on keyword column if FTS returns nothing
      3. Fetch full note content for matched note IDs
      4. Return NoteContext (found=False if nothing matched)
    """
    tokens = _tokenise_query(query)
    if not tokens:
        return NoteContext(found=False, matched_keywords=[], concepts=[], note_snippets=[], note_titles=[])

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # ── Stage 1: FTS5 search ────────────────────────────────────────
            fts_query = _build_fts_query(tokens)
            try:
                rows = await (
                    await db.execute(
                        """
                        SELECT ni.note_id, ni.profile_id, ni.keyword, ni.concept, ni.snippet
                        FROM note_index ni
                        JOIN note_index_fts fts ON fts.rowid = ni.id
                        WHERE note_index_fts MATCH ?
                          AND ni.profile_id = ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_query, profile_id, _MAX_NOTES * 3),
                    )
                ).fetchall()
            except Exception:
                # FTS table may not exist yet (no notes indexed) — return empty
                rows = []

            # ── Stage 2: LIKE fallback ──────────────────────────────────────
            if not rows:
                like_conditions = " OR ".join(
                    ["ni.keyword LIKE ? OR ni.concept LIKE ?"] * len(tokens)
                )
                params: list = []
                for t in tokens:
                    params.extend([f"%{t}%", f"%{t}%"])
                params.extend([profile_id, _MAX_NOTES * 3])

                try:
                    rows = await (
                        await db.execute(
                            f"""
                            SELECT note_id, profile_id, keyword, concept, snippet
                            FROM note_index ni
                            WHERE ({like_conditions})
                              AND ni.profile_id = ?
                            ORDER BY created_at DESC
                            LIMIT ?
                            """,
                            params,
                        )
                    ).fetchall()
                except Exception as exc:
                    logger.warning("LIKE fallback query failed: %s", exc)
                    rows = []

            if not rows:
                return NoteContext(
                    found=False, matched_keywords=[], concepts=[], note_snippets=[], note_titles=[]
                )

            # Deduplicate by note_id, keeping the first (highest ranked) match per note
            seen_note_ids: dict[int, dict] = {}
            for row in rows:
                nid = row["note_id"]
                if nid not in seen_note_ids:
                    seen_note_ids[nid] = dict(row)
                if len(seen_note_ids) >= _MAX_NOTES:
                    break

            matched_note_ids = list(seen_note_ids.keys())

            # Fetch full note content
            note_map = await _fetch_note_content(db, matched_note_ids)

            # Build result
            matched_keywords: list[str] = []
            concepts: list[str] = []
            snippets: list[str] = []
            titles: list[str] = []

            for nid in matched_note_ids:
                index_row = seen_note_ids[nid]
                matched_keywords.append(index_row["keyword"])
                concepts.append(index_row["concept"])

                if nid in note_map:
                    title, content = note_map[nid]
                    titles.append(title)
                    # Truncate content so the prompt stays manageable
                    snippets.append(content[:_MAX_CONTENT_CHARS])
                else:
                    # Fall back to the stored snippet from index
                    titles.append("Note")
                    snippets.append(index_row["snippet"])

            logger.info(
                "Note retrieval for profile %d | query=%r | matched notes=%s | keywords=%s",
                profile_id,
                query[:60],
                matched_note_ids,
                matched_keywords,
            )

            return NoteContext(
                found=True,
                matched_keywords=matched_keywords,
                concepts=concepts,
                note_snippets=snippets,
                note_titles=titles,
            )

    except Exception as exc:
        logger.exception("Note retrieval failed: %s", exc)
        return NoteContext(found=False, matched_keywords=[], concepts=[], note_snippets=[], note_titles=[])
