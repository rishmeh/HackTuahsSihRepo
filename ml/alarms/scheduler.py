"""
scheduler.py — APScheduler polls timers/alarms every 5 s.

Laptop-only mode (PI_HOST empty — the default):
  1. Broadcasts a WebSocket event to all connected browser tabs.
  2. Plays a system beep via winsound (Windows) / afplay (macOS) / paplay (Linux).

Pi mode (PI_HOST set in ml/.env):
  Steps 1 + 2 above, PLUS POSTs to the Pi Flask server.
"""
from __future__ import annotations
import asyncio, logging, os
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from alarms.store import (
    get_active_alarms, get_active_timers,
    mark_alarm_fired, mark_timer_fired,
)
from ws_manager import manager

logger = logging.getLogger(__name__)
PI_HOST: str = os.getenv("PI_HOST", "")
PI_PORT: int = int(os.getenv("PI_PORT", "5000"))

_scheduler = AsyncIOScheduler()


async def _laptop_beep() -> None:
    """Audible alert on the laptop itself (no Pi required)."""
    def _beep():
        try:
            import winsound
            winsound.Beep(880, 1500)
            return
        except ImportError:
            pass
        import subprocess
        for cmd in (
            ["afplay", "/System/Library/Sounds/Glass.aiff"],
            ["paplay", "/usr/share/sounds/alsa/Bell.wav"],
            ["aplay",  "/usr/share/sounds/alsa/Front_Center.wav"],
        ):
            try:
                subprocess.call(cmd, timeout=3)
                return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _beep)
    except Exception as exc:
        logger.debug("Laptop beep error: %s", exc)


async def _notify_pi(payload: dict) -> None:
    if not PI_HOST:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(f"http://{PI_HOST}:{PI_PORT}/alarm/ring", json=payload)
    except Exception as exc:
        logger.warning("Could not reach Pi: %s", exc)


async def _check() -> None:
    now = datetime.now(timezone.utc)

    try:
        for alarm in await get_active_alarms():
            tgt = alarm.get("targetAt") or alarm.get("target_at")
            if not tgt:
                continue
            if datetime.fromtimestamp(tgt / 1000, tz=timezone.utc) <= now:
                aid, label, repeat = alarm["id"], alarm.get("label", "Alarm"), alarm.get("repeatDays")
                logger.info("Alarm %d ('%s') firing.", aid, label)
                await manager.broadcast({"type": "alarm_fired", "alarm_id": aid, "label": label})
                asyncio.ensure_future(_laptop_beep())
                await _notify_pi({"alarm_id": aid, "label": label})
                await mark_alarm_fired(aid, repeat)
    except Exception as exc:
        logger.error("Alarm check error: %s", exc)

    try:
        for timer in await get_active_timers():
            if timer.get("status") != "running":
                continue
            tgt = timer.get("targetAt") or timer.get("target_at")
            if not tgt:
                continue
            if datetime.fromtimestamp(tgt / 1000, tz=timezone.utc) <= now:
                tid, label = timer["id"], timer.get("label", "Timer")
                logger.info("Timer %d ('%s') completed.", tid, label)
                await manager.broadcast({"type": "timer_fired", "timer_id": tid, "label": label})
                asyncio.ensure_future(_laptop_beep())
                await _notify_pi({"timer_id": tid, "label": label})
                await mark_timer_fired(tid)
    except Exception as exc:
        logger.error("Timer check error: %s", exc)


def start_scheduler() -> None:
    _scheduler.add_job(
        _check, "interval", seconds=5, id="alarm_poll", max_instances=1, coalesce=True
    )
    _scheduler.start()
    logger.info(
        "Alarm/timer scheduler started (5 s poll). Pi=%s",
        PI_HOST or "not configured — laptop-only mode",
    )
