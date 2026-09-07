"""Async SQLite helpers for timers and alarms (shared tabletot.db)."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"


async def _tables() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ownerProfileId INTEGER NOT NULL DEFAULT 0,
                label TEXT NOT NULL DEFAULT 'Timer',
                durationSeconds INTEGER NOT NULL,
                targetAt INTEGER,
                status TEXT NOT NULL DEFAULT 'idle',
                remainingSeconds INTEGER,
                createdAt INTEGER NOT NULL,
                updatedAt INTEGER NOT NULL
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ownerProfileId INTEGER NOT NULL DEFAULT 0,
                label TEXT NOT NULL DEFAULT 'Alarm',
                targetAt INTEGER NOT NULL,
                repeatDays TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                snoozedUntil INTEGER,
                createdAt INTEGER NOT NULL,
                updatedAt INTEGER NOT NULL
            )"""
        )
        await db.commit()


def _ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


async def create_timer(label: str, duration_seconds: int, profile_id: Optional[int]) -> dict:
    await _tables()
    now = _ms()
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO timers (ownerProfileId,label,durationSeconds,status,createdAt,updatedAt) "
            "VALUES (?,?,?,'idle',?,?)",
            (profile_id or 0, label, duration_seconds, now, now),
        )
        await db.commit()
        return {"id": c.lastrowid, "label": label, "duration_seconds": duration_seconds, "status": "idle"}


async def start_timer(timer_id: int) -> dict:
    await _tables()
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT durationSeconds FROM timers WHERE id=?", (timer_id,)
        )).fetchone()
        if not row:
            raise ValueError(f"Timer {timer_id} not found")
        dur = row[0]
        target = datetime.now(timezone.utc) + timedelta(seconds=dur)
        target_ms = int(target.timestamp() * 1000)
        await db.execute(
            "UPDATE timers SET status='running',targetAt=?,remainingSeconds=?,updatedAt=? WHERE id=?",
            (target_ms, dur, _ms(), timer_id),
        )
        await db.commit()
        return {"id": timer_id, "target_at": target.isoformat(), "status": "running"}


async def pause_timer(timer_id: int) -> dict:
    await _tables()
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT targetAt FROM timers WHERE id=?", (timer_id,)
        )).fetchone()
        if not row or not row[0]:
            raise ValueError(f"Timer {timer_id} not running")
        remaining = max(0, (row[0] - _ms()) // 1000)
        await db.execute(
            "UPDATE timers SET status='paused',remainingSeconds=?,updatedAt=? WHERE id=?",
            (remaining, _ms(), timer_id),
        )
        await db.commit()
        return {"id": timer_id, "remaining_seconds": remaining, "status": "paused"}


async def cancel_timer(timer_id: int) -> None:
    await _tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE timers SET status='cancelled',updatedAt=? WHERE id=?", (_ms(), timer_id)
        )
        await db.commit()


async def mark_timer_fired(timer_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE timers SET status='fired',updatedAt=? WHERE id=?", (_ms(), timer_id)
        )
        await db.commit()


async def get_active_timers() -> list[dict]:
    await _tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM timers WHERE status IN ('running','paused')"
        )).fetchall()
        return [dict(r) for r in rows]


async def create_alarm(
    label: str, target_at: datetime, repeat_days: Optional[list], profile_id: Optional[int]
) -> dict:
    await _tables()
    now = _ms()
    target_ms = int(target_at.timestamp() * 1000)
    repeat_json = json.dumps(repeat_days) if repeat_days else None
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO alarms (ownerProfileId,label,targetAt,repeatDays,status,createdAt,updatedAt) "
            "VALUES (?,?,?,?,'active',?,?)",
            (profile_id or 0, label, target_ms, repeat_json, now, now),
        )
        await db.commit()
        return {
            "id": c.lastrowid, "label": label,
            "target_at": target_at.isoformat(), "repeat_days": repeat_days, "status": "active",
        }


async def get_active_alarms() -> list[dict]:
    await _tables()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM alarms WHERE status='active'"
        )).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("repeatDays"):
                d["repeatDays"] = json.loads(d["repeatDays"])
            result.append(d)
        return result


async def snooze_alarm(alarm_id: int, minutes: int) -> dict:
    await _tables()
    new_target = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    new_ms = int(new_target.timestamp() * 1000)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alarms SET targetAt=?,status='active',snoozedUntil=?,updatedAt=? WHERE id=?",
            (new_ms, new_ms, _ms(), alarm_id),
        )
        await db.commit()
    return {"id": alarm_id, "snoozed_until": new_target.isoformat()}


async def cancel_alarm(alarm_id: int) -> None:
    await _tables()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE alarms SET status='cancelled',updatedAt=? WHERE id=?", (_ms(), alarm_id)
        )
        await db.commit()


async def mark_alarm_fired(alarm_id: int, repeat_days: Optional[list]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if repeat_days:
            now = datetime.now(timezone.utc)
            for offset in range(1, 8):
                candidate = now + timedelta(days=offset)
                if candidate.weekday() in repeat_days:
                    row = await (await db.execute(
                        "SELECT targetAt FROM alarms WHERE id=?", (alarm_id,)
                    )).fetchone()
                    if row and row[0]:
                        old = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
                        new_t = candidate.replace(
                            hour=old.hour, minute=old.minute, second=0, microsecond=0
                        )
                        await db.execute(
                            "UPDATE alarms SET targetAt=?,status='active',updatedAt=? WHERE id=?",
                            (int(new_t.timestamp() * 1000), _ms(), alarm_id),
                        )
                        await db.commit()
                        return
                    break
        await db.execute(
            "UPDATE alarms SET status='fired',updatedAt=? WHERE id=?", (_ms(), alarm_id)
        )
        await db.commit()
