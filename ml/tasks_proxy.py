"""
tasks_proxy.py — Read/write task endpoint for the ML backend.

The Node tRPC backend owns the authoritative task UI and mutations
exposed to the dashboard. This module provides a lightweight parallel
endpoint so the voice dispatcher can list AND create tasks without
coupling to the Node server's tRPC protocol.

GET  /tasks_proxy/{profile_id}          list tasks (read-only)
POST /tasks_proxy/{profile_id}          create a task
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/tasks_proxy", tags=["Tasks Proxy"])
DB_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "data" / "tabletot.db"


class TaskCreate(BaseModel):
    title: str
    subject: str = "Personal"
    due: str = "Today"
    color: str = "gold"


def _ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


@router.get("/{profile_id}", summary="List tasks for a profile (read-only)")
async def list_tasks(profile_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id,title,subject,due,done,color,priority "
            "FROM tasks WHERE ownerProfileId=? ORDER BY position,id",
            (profile_id,),
        )).fetchall()
        return [dict(r) for r in rows]


@router.post("/{profile_id}", summary="Create a task (voice-triggered)")
async def create_task(profile_id: int, body: TaskCreate):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "title is required")

    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT COALESCE(MAX(position), -1) FROM tasks WHERE ownerProfileId=?",
            (profile_id,),
        )).fetchone()
        next_pos = (row[0] if row else -1) + 1
        now = _ms()
        cursor = await db.execute(
            "INSERT INTO tasks "
            "(ownerProfileId, title, subject, due, done, color, position, createdAt, updatedAt) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (profile_id, title, body.subject, body.due, body.color, next_pos, now, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "title": title,
            "subject": body.subject,
            "due": body.due,
            "color": body.color,
            "done": False,
            "profile_id": profile_id,
        }
