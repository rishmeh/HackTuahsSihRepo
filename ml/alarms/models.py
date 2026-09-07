from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class TimerCreate(BaseModel):
    label: str = "Timer"
    duration_seconds: int
    profile_id: Optional[int] = None


class AlarmCreate(BaseModel):
    label: str = "Alarm"
    target_at: datetime
    repeat_days: Optional[List[int]] = None
    profile_id: Optional[int] = None


class SnoozeRequest(BaseModel):
    minutes: int = 5
