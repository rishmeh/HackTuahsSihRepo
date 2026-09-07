"""GET /weather?location=Chennai — OWM with 10-minute SQLite cache."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiosqlite, httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/weather", tags=["Weather"])
OWM_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")
DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"
CACHE_TTL = timedelta(minutes=10)


async def _ensure():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS weatherCache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL UNIQUE,
                data TEXT NOT NULL,
                fetchedAt INTEGER NOT NULL
            )"""
        )
        await db.commit()


async def _cached(loc: str) -> dict | None:
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT data,fetchedAt FROM weatherCache WHERE location=?", (loc.lower(),)
        )).fetchone()
        if not row:
            return None
        if datetime.now(timezone.utc) - datetime.fromtimestamp(row["fetchedAt"] / 1000, tz=timezone.utc) > CACHE_TTL:
            return None
        return json.loads(row["data"])


async def _store(loc: str, data: dict):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO weatherCache (location,data,fetchedAt) VALUES (?,?,?)
               ON CONFLICT(location) DO UPDATE SET data=excluded.data,fetchedAt=excluded.fetchedAt""",
            (loc.lower(), json.dumps(data), now),
        )
        await db.commit()


@router.get("/")
async def get_weather(location: str = Query(..., min_length=1, max_length=100)):
    cached = await _cached(location)
    if cached:
        return {**cached, "cached": True}

    if not OWM_KEY:
        raise HTTPException(
            503,
            detail="Set OPENWEATHERMAP_API_KEY in ml/.env (free at openweathermap.org)",
        )

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": location, "appid": OWM_KEY, "units": "metric"},
        )

    if r.status_code == 404:
        raise HTTPException(404, f"Location '{location}' not found")
    if r.status_code != 200:
        raise HTTPException(502, f"OWM error: {r.text}")

    data = r.json()
    await _store(location, data)
    return {**data, "cached": False}
