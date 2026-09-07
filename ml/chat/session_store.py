"""
chat/session_store.py — In-memory + SQLite conversation history.
Existing public interface is unchanged; adds async SQLite persistence.
"""
from __future__ import annotations
import asyncio, logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque

import aiosqlite
import config

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"


@dataclass
class Turn:
    user: str
    assistant: str


_sessions: dict[str, Deque[Turn]] = {}


async def _ensure_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS chatHistory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sessionId TEXT NOT NULL,
                ownerProfileId INTEGER,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                createdAt INTEGER NOT NULL
            )"""
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS chatHistory_sid ON chatHistory (sessionId)"
        )
        await db.commit()


async def _persist(session_id: str, user_msg: str, assistant_msg: str, source: str = "slm"):
    try:
        await _ensure_table()
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO chatHistory (sessionId,role,content,source,createdAt) VALUES (?,?,?,?,?)",
                (session_id, "user", user_msg, None, now),
            )
            await db.execute(
                "INSERT INTO chatHistory (sessionId,role,content,source,createdAt) VALUES (?,?,?,?,?)",
                (session_id, "assistant", assistant_msg, source, now),
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to persist turn for %s: %s", session_id, exc)


async def get_history_from_db(session_id: str, limit: int = 50) -> list[dict]:
    try:
        await _ensure_table()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(
                "SELECT role,content,source,createdAt FROM chatHistory "
                "WHERE sessionId=? ORDER BY createdAt DESC LIMIT ?",
                (session_id, limit),
            )).fetchall()
        return [dict(r) for r in reversed(rows)]
    except Exception as exc:
        logger.warning("Failed to read history for %s: %s", session_id, exc)
        return []


def append_turn(session_id: str, user_msg: str, assistant_msg: str, source: str = "slm") -> None:
    if not session_id:
        return
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=config.MAX_HISTORY_TURNS)
    _sessions[session_id].append(Turn(user=user_msg, assistant=assistant_msg))
    logger.debug("Session %s: %d turn(s).", session_id, len(_sessions[session_id]))
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_persist(session_id, user_msg, assistant_msg, source))
    except RuntimeError:
        pass


def get_history(session_id: str) -> list[Turn]:
    if not session_id or session_id not in _sessions:
        return []
    return list(_sessions[session_id])


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    logger.info("Session %s cleared.", session_id)


def history_as_messages(session_id: str) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    for turn in get_history(session_id):
        msgs.append({"role": "user", "content": turn.user})
        msgs.append({"role": "assistant", "content": turn.assistant})
    return msgs
