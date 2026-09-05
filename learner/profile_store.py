"""
learner/profile_store.py — Persists learner profiles, one per student.

SQLite, one row per student, the profile stored as JSON. The raw answers are
inside the profile, so if the scoring rules change every student can be
rescored without being asked the questions again.

This table is the first piece of what IMPLEMENTATION_PLAN.md calls the
students database. When that arrives, this becomes one of its tables; the
student_id here is the key that will join it to face embeddings and sessions.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from learner.models import LearnerProfile

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learner_profiles (
    student_id  TEXT PRIMARY KEY,
    profile     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@dataclass(frozen=True)
class StoredProfile:
    student_id: str
    profile: LearnerProfile
    updated_at: str


class ProfileStore:
    """One connection per operation — safe across the API's worker threads."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save(self, student_id: str, profile: LearnerProfile) -> None:
        """Insert or replace the profile for a student."""
        payload = profile.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learner_profiles (student_id, profile)
                VALUES (?, ?)
                ON CONFLICT(student_id) DO UPDATE SET
                    profile = excluded.profile,
                    updated_at = datetime('now')
                """,
                (student_id, payload),
            )
        logger.info("Saved learner profile for %r (%d answers)", student_id, profile.answered)

    def get(self, student_id: str) -> StoredProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile, updated_at FROM learner_profiles WHERE student_id = ?",
                (student_id,),
            ).fetchone()
        if row is None:
            return None
        # pydantic coerces the JSON's string keys back to int for dict[int, str].
        return StoredProfile(
            student_id=student_id,
            profile=LearnerProfile.model_validate_json(row[0]),
            updated_at=row[1],
        )

    def delete(self, student_id: str) -> bool:
        """Erase a student's profile. Returns whether anything was removed."""
        with self._connect() as conn:
            removed = conn.execute(
                "DELETE FROM learner_profiles WHERE student_id = ?", (student_id,)
            ).rowcount
        if removed:
            logger.info("Deleted learner profile for %r", student_id)
        return removed > 0

    def list_students(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT student_id FROM learner_profiles ORDER BY student_id"
            ).fetchall()
        return [r[0] for r in rows]
