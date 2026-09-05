"""
vision/face_store.py — On-device database of enrolled face embeddings.

This is the privacy boundary of the project. The deck promises that no face
image is ever stored or uploaded; this module is what makes that true. The
schema has exactly one place to put face data — a BLOB of 128 float32 values —
and there is no code path that writes a frame to disk.

An embedding is not reversible into a photograph. It is a direction in
128-dimensional space that happens to be similar for the same person. Losing
the database leaks far less than losing a folder of student photos would.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import numpy as np

from vision.models import EnrolledFace

logger = logging.getLogger(__name__)

# SFace produces a 128-dimensional embedding. Enforced on write so a mismatched
# model swap fails loudly at enrolment rather than silently never matching.
EMBEDDING_DIM = 128

_SCHEMA = """
CREATE TABLE IF NOT EXISTS faces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT    NOT NULL,
    embedding   BLOB    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_faces_student ON faces(student_id);
"""


class FaceStore:
    """
    SQLite-backed store of face embeddings, keyed by student.

    Opens a fresh connection per operation rather than holding one open: the
    vision loop and the FastAPI request handlers run on different threads, and
    a single shared SQLite connection is not safe across them.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # -- writing ------------------------------------------------------------

    def add_embedding(self, student_id: str, embedding: np.ndarray) -> None:
        """Store one embedding for a student."""
        self.add_embeddings(student_id, [embedding])

    def add_embeddings(
        self, student_id: str, embeddings: list[np.ndarray]
    ) -> int:
        """
        Store several embeddings for a student and return how many were saved.

        Raises:
            ValueError: If any embedding is not EMBEDDING_DIM long.
        """
        rows = [(student_id, _to_blob(e)) for e in embeddings]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO faces (student_id, embedding) VALUES (?, ?)", rows
            )
        logger.info("Enrolled %d embedding(s) for student %r", len(rows), student_id)
        return len(rows)

    def delete_student(self, student_id: str) -> int:
        """Erase every embedding for a student. Returns how many were removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM faces WHERE student_id = ?", (student_id,)
            )
            removed = cursor.rowcount
        logger.info("Deleted %d embedding(s) for student %r", removed, student_id)
        return removed

    # -- reading ------------------------------------------------------------

    def load_gallery(self) -> list[EnrolledFace]:
        """
        Load every enrolled student and their embeddings.

        Called once at start-up and again after enrolment — matching then runs
        against the in-memory gallery, so no disk read happens per frame.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT student_id, embedding FROM faces ORDER BY student_id, id"
            ).fetchall()

        grouped: dict[str, list[np.ndarray]] = {}
        for student_id, blob in rows:
            grouped.setdefault(student_id, []).append(_from_blob(blob))

        return [
            EnrolledFace(student_id=sid, embeddings=vectors)
            for sid, vectors in grouped.items()
        ]

    def list_students(self) -> list[str]:
        """Every enrolled student id, alphabetically."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT student_id FROM faces ORDER BY student_id"
            ).fetchall()
        return [r[0] for r in rows]

    def count_embeddings(self, student_id: str) -> int:
        """How many embeddings are enrolled for one student."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM faces WHERE student_id = ?", (student_id,)
            ).fetchone()
        return int(row[0])

    def column_names(self) -> list[str]:
        """Column names of the faces table — used to audit the privacy promise."""
        with self._connect() as conn:
            rows = conn.execute("PRAGMA table_info(faces)").fetchall()
        return [r[1] for r in rows]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _to_blob(embedding: np.ndarray) -> bytes:
    """
    Pack an embedding into raw float32 bytes.

    float32 is stored rather than a text or JSON encoding so the round trip is
    exact — a rounded embedding shifts similarity scores, and the threshold is
    tuned to three decimal places.
    """
    vector = np.asarray(embedding, dtype=np.float32).ravel()
    if vector.size != EMBEDDING_DIM:
        raise ValueError(
            f"expected a {EMBEDDING_DIM}-d embedding, got {vector.size}-d — "
            "is the recognition model the expected SFace one?"
        )
    return vector.tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    """Unpack raw float32 bytes back into an embedding."""
    return np.frombuffer(blob, dtype=np.float32)
