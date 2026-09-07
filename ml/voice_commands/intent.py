"""Regex intent parser — runs before the LLM, zero latency."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Intent:
    name: str
    params: dict = field(default_factory=dict)


# ── CREATE intents ────────────────────────────────────────────────────────────
_TIMER   = re.compile(r"(?:set|start|create)\s+(?:a\s+)?timer\s+for\s+(\d+)\s*(hour|hr|minute|min|second|sec)s?", re.I)
_ALARM   = re.compile(r"(?:set|create|add|wake\s+me(?:\s+up)?)\s+(?:an?\s+)?alarm\s+(?:at|for)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)
_WEATHER = re.compile(r"weather\s+(?:in|for|today)|what(?:'s|s| is)\s+the\s+weather|how(?:'s|s| is)\s+the\s+weather", re.I)
_LOCATION= re.compile(r"(?:weather\s+(?:in|for|at)|in|at|for)\s+([A-Za-z][A-Za-z\s]{1,40}?)(?:\?|$|\.|,)", re.I)
_TIME    = re.compile(r"what(?:'s|s| is)\s+the\s+(?:current\s+)?time|time\s+(?:is\s+it|now)|current\s+time", re.I)
_NOTE    = re.compile(r"(?:add|take|save|make|create)\s+a?\s*note[:\s]+(.+)", re.I)

# ── LIST / QUERY intents ──────────────────────────────────────────────────────
_LIST_TIMERS = re.compile(
    r"(?:what|show|list|tell\s+me|check|do\s+i\s+have)\s+(?:my\s+)?timers?"
    r"|list\s+(?:all\s+)?timers?"
    r"|what\s+timers?\s+(?:do\s+i\s+have|are\s+(?:there|running|set))", re.I)
_LIST_ALARMS = re.compile(
    r"(?:what|show|list|tell\s+me|check|do\s+i\s+have)\s+(?:my\s+)?alarms?"
    r"|list\s+(?:all\s+)?alarms?"
    r"|what\s+alarms?\s+(?:do\s+i\s+have|are\s+(?:there|set))", re.I)
_LIST_NOTES  = re.compile(
    r"(?:what|show|list|tell\s+me|read|check|do\s+i\s+have)\s+(?:my\s+)?notes?"
    r"|list\s+(?:all\s+)?(?:my\s+)?notes?"
    r"|what\s+notes?\s+(?:do\s+i\s+have|are\s+there)", re.I)
_LIST_TASKS  = re.compile(
    r"(?:what|show|list|tell\s+me|check|do\s+i\s+have)\s+(?:my\s+)?(?:tasks?|to-?dos?|to-?do\s+list)"
    r"|list\s+(?:all\s+)?(?:my\s+)?(?:tasks?|to-?dos?)"
    r"|what(?:'s| is)\s+on\s+my\s+(?:to-?do|task)(?:\s+list)?"
    r"|(?:tasks?|to-?dos?)\s+(?:do\s+i\s+have|are\s+(?:there|pending))", re.I)


def parse(text: str) -> Intent:
    # List queries first (more specific — check before create patterns)
    if _LIST_TIMERS.search(text): return Intent("list_timers")
    if _LIST_ALARMS.search(text): return Intent("list_alarms")
    if _LIST_NOTES.search(text):  return Intent("list_notes")
    if _LIST_TASKS.search(text):  return Intent("list_tasks")

    # Single-value queries
    if _TIME.search(text):
        return Intent("get_time")

    if _WEATHER.search(text):
        loc_m = _LOCATION.search(text)
        return Intent("get_weather", {"location": loc_m.group(1).strip() if loc_m else ""})

    # Create actions
    if m := _TIMER.search(text):
        amount, unit = int(m.group(1)), m.group(2).lower()
        secs = amount * {"hour": 3600, "hr": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}[unit]
        return Intent("set_timer", {"duration_seconds": secs, "label": f"{amount} {unit} timer"})

    if m := _ALARM.search(text):
        h, mn, mer = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if mer == "pm" and h != 12: h += 12
        elif mer == "am" and h == 12: h = 0
        target = datetime.now().replace(hour=h, minute=mn, second=0, microsecond=0)
        if target <= datetime.now(): target += timedelta(days=1)
        return Intent("set_alarm", {"target_at": target.isoformat(), "label": f"Alarm at {h:02d}:{mn:02d}"})

    if m := _NOTE.search(text):
        return Intent("add_note", {"content": m.group(1).strip()})

    return Intent("unknown")
