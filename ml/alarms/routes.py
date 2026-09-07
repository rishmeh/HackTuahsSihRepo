from __future__ import annotations
from fastapi import APIRouter, HTTPException
from .models import TimerCreate, AlarmCreate, SnoozeRequest
from . import store

router = APIRouter(prefix="/alarms", tags=["Alarms & Timers"])


@router.post("/timers")
async def create_timer(body: TimerCreate):
    return await store.create_timer(body.label, body.duration_seconds, body.profile_id)


@router.post("/timers/{timer_id}/start")
async def start_timer(timer_id: int):
    try:
        return await store.start_timer(timer_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/timers/{timer_id}/pause")
async def pause_timer(timer_id: int):
    try:
        return await store.pause_timer(timer_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/timers/{timer_id}")
async def cancel_timer(timer_id: int):
    await store.cancel_timer(timer_id)
    return {"cancelled": timer_id}


@router.get("/timers")
async def list_timers():
    return await store.get_active_timers()


@router.post("/")
async def create_alarm(body: AlarmCreate):
    return await store.create_alarm(body.label, body.target_at, body.repeat_days, body.profile_id)


@router.get("/")
async def list_alarms():
    return await store.get_active_alarms()


@router.post("/{alarm_id}/snooze")
async def snooze_alarm(alarm_id: int, body: SnoozeRequest):
    return await store.snooze_alarm(alarm_id, body.minutes)


@router.delete("/{alarm_id}")
async def cancel_alarm(alarm_id: int):
    await store.cancel_alarm(alarm_id)
    return {"cancelled": alarm_id}
