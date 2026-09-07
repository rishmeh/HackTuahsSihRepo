"""Read-only task endpoint for the voice dispatcher."""
from __future__ import annotations
from pathlib import Path
import aiosqlite
from fastapi import APIRouter

router = APIRouter(prefix="/tasks_proxy", tags=["Tasks Proxy"])
DB_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "data" / "tabletot.db"


@router.get("/{profile_id}")
async def list_tasks(profile_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id,title,subject,due,done,color,priority FROM tasks "
            "WHERE ownerProfileId=? ORDER BY position,id",
            (profile_id,),
        )).fetchall()
        return [dict(r) for r in rows]
