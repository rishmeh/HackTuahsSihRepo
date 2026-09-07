"""Full CRUD for sticky notes in the shared SQLite database."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/notes", tags=["Notes"])
DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"


class NoteCreate(BaseModel):
    owner_profile_id: int = 0
    title: str = "Untitled"
    content: str = ""
    tags: Optional[list[str]] = None
    color: str = "yellow"


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    is_pinned: Optional[bool] = None
    color: Optional[str] = None


async def _ensure():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ownerProfileId INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT 'Untitled',
                content TEXT NOT NULL DEFAULT '',
                tags TEXT,
                isPinned INTEGER NOT NULL DEFAULT 0,
                color TEXT NOT NULL DEFAULT 'yellow',
                createdAt INTEGER NOT NULL,
                updatedAt INTEGER NOT NULL
            )"""
        )
        await db.commit()


def _ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


@router.post("/")
async def create_note(body: NoteCreate):
    await _ensure()
    now = _ms()
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO notes (ownerProfileId,title,content,tags,color,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?)",
            (body.owner_profile_id, body.title, body.content,
             json.dumps(body.tags) if body.tags else None, body.color, now, now),
        )
        await db.commit()
        return {"id": c.lastrowid, **body.model_dump()}


@router.get("/{profile_id}")
async def list_notes(profile_id: int):
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM notes WHERE ownerProfileId=? ORDER BY isPinned DESC,updatedAt DESC",
            (profile_id,),
        )).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
            result.append(d)
        return result


@router.put("/{note_id}")
async def update_note(note_id: int, body: NoteUpdate):
    await _ensure()
    now = _ms()
    sets, vals = [], []
    if body.title is not None:    sets.append("title=?");    vals.append(body.title)
    if body.content is not None:  sets.append("content=?");  vals.append(body.content)
    if body.tags is not None:     sets.append("tags=?");     vals.append(json.dumps(body.tags))
    if body.is_pinned is not None: sets.append("isPinned=?"); vals.append(int(body.is_pinned))
    if body.color is not None:    sets.append("color=?");    vals.append(body.color)
    if not sets:
        raise HTTPException(400, "Nothing to update")
    sets.append("updatedAt=?"); vals.append(now); vals.append(note_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE notes SET {', '.join(sets)} WHERE id=?", vals)
        await db.commit()
    return {"updated": note_id}


@router.delete("/{note_id}")
async def delete_note(note_id: int):
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM notes WHERE id=?", (note_id,))
        await db.commit()
    return {"deleted": note_id}
