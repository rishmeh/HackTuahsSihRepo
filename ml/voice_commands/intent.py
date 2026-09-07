"""Regex intent parser — runs before the LLM, zero latency.

Handles digit numbers AND spoken word numbers so STT output like
"set a timer for ten minutes" is correctly parsed.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Intent:
    name: str
    params: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Word-number helpers
# ---------------------------------------------------------------------------

_WORD_TO_NUM: dict[str, float] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "twenty one": 21, "twenty two": 22, "twenty three": 23,
    "twenty four": 24, "twenty five": 25, "twenty six": 26, "twenty seven": 27,
    "twenty eight": 28, "twenty nine": 29, "thirty": 30, "forty": 40,
    "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90,
    "half": 0.5,
}

_WORD_NUM_PAT = "|".join(
    re.escape(k) for k in sorted(_WORD_TO_NUM, key=len, reverse=True)
)

def _to_num(s: str) -> float:
    s = s.strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    return _WORD_TO_NUM.get(s, 1)


# ---------------------------------------------------------------------------
# Alarm time helpers — understand "seven thirty", "half past nine", etc.
# ---------------------------------------------------------------------------

_HOUR_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_MINUTE_WORDS = {
    "oh": 0, "zero": 0, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20,
    "twenty five": 25, "thirty": 30, "thirty five": 35, "forty": 40,
    "forty five": 45, "fifty": 50, "fifty five": 55, "o'clock": 0,
    "quarter": 15, "half": 30,
}


# ---------------------------------------------------------------------------
# CREATE intents
# ---------------------------------------------------------------------------

_NUM_PAT = rf"(\d+|{_WORD_NUM_PAT})"
_UNIT_PAT = r"(hour|hr|minute|min|second|sec)s?"

_TIMER = re.compile(
    rf"(?:set|start|create|put)\s+(?:a\s+)?timer\s+for\s+{_NUM_PAT}\s*{_UNIT_PAT}",
    re.I,
)
# Also catch "timer: ten minutes" or "ten minute timer"
_TIMER_ALT = re.compile(
    rf"{_NUM_PAT}\s*[- ]?{_UNIT_PAT}\s+timer",
    re.I,
)

_ALARM_DIGIT = re.compile(
    r"(?:set|create|add|wake\s+me(?:\s+up)?)\s+(?:an?\s+)?alarm\s+(?:at|for)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.I,
)
_ALARM_WORD = re.compile(
    r"(?:set|create|add|wake\s+me(?:\s+up)?)\s+(?:an?\s+)?alarm\s+(?:at|for)?\s*"
    r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"(?:\s+(thirty|forty five|quarter|half|fifteen|twenty|twenty five|forty|fifty|fifty five|oh|zero))?"
    r"\s*(am|pm)?",
    re.I,
)

_WEATHER = re.compile(
    r"weather\s+(?:in|for|today)|what(?:'s|s| is)\s+the\s+weather|how(?:'s|s| is)\s+the\s+weather",
    re.I,
)
_LOCATION = re.compile(
    r"(?:weather\s+(?:in|for|at)|in|at|for)\s+([A-Za-z][A-Za-z\s]{1,40}?)(?:\?|$|\.|,)",
    re.I,
)
_TIME = re.compile(
    r"what(?:'s|s| is)\s+the\s+(?:current\s+)?time|time\s+(?:is\s+it|now)|current\s+time",
    re.I,
)
_NOTE = re.compile(r"(?:add|take|save|make|create)\s+a?\s*note[:\s]+(.+)", re.I)

# ---------------------------------------------------------------------------
# LIST / QUERY intents
# ---------------------------------------------------------------------------

_LIST_TIMERS = re.compile(
    r"(?:what|show|list|tell\s+me|check|do\s+i\s+have)\s+(?:my\s+)?timers?"
    r"|list\s+(?:all\s+)?timers?"
    r"|what\s+timers?\s+(?:do\s+i\s+have|are\s+(?:there|running|set))", re.I)
_LIST_ALARMS = re.compile(
    r"(?:what|show|list|tell\s+me|check|do\s+i\s+have)\s+(?:my\s+)?alarms?"
    r"|list\s+(?:all\s+)?alarms?"
    r"|what\s+alarms?\s+(?:do\s+i\s+have|are\s+(?:there|set))", re.I)
_LIST_NOTES = re.compile(
    r"(?:what|show|list|tell\s+me|read|check|do\s+i\s+have)\s+(?:my\s+)?notes?"
    r"|list\s+(?:all\s+)?(?:my\s+)?notes?"
    r"|what\s+notes?\s+(?:do\s+i\s+have|are\s+there)", re.I)
_LIST_TASKS = re.compile(
    r"(?:what|show|list|tell\s+me|check|do\s+i\s+have)\s+(?:my\s+)?(?:tasks?|to-?dos?|to-?do\s+list)"
    r"|list\s+(?:all\s+)?(?:my\s+)?(?:tasks?|to-?dos?)"
    r"|what(?:'s| is)\s+on\s+my\s+(?:to-?do|task)(?:\s+list)?"
    r"|(?:tasks?|to-?dos?)\s+(?:do\s+i\s+have|are\s+(?:there|pending))", re.I)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(text: str) -> Intent:
    """
    Parse a voice utterance into a structured Intent.
    Returns Intent("unknown") when no pattern matches — caller should then
    try the LLM router before falling through to the full chat pipeline.
    """
    # ── List queries (check before create to avoid false matches) ────────────
    if _LIST_TIMERS.search(text): return Intent("list_timers")
    if _LIST_ALARMS.search(text): return Intent("list_alarms")
    if _LIST_NOTES.search(text):  return Intent("list_notes")
    if _LIST_TASKS.search(text):  return Intent("list_tasks")

    # ── Instant lookups ───────────────────────────────────────────────────────
    if _TIME.search(text):
        return Intent("get_time")

    if _WEATHER.search(text):
        loc_m = _LOCATION.search(text)
        return Intent("get_weather", {"location": loc_m.group(1).strip() if loc_m else ""})

    # ── Timer (digit or word) ────────────────────────────────────────────────
    m = _TIMER.search(text) or _TIMER_ALT.search(text)
    if m:
        raw, unit = m.group(1), m.group(2).lower()
        amount = _to_num(raw)
        multipliers = {"hour": 3600, "hr": 3600, "minute": 60, "min": 60, "second": 1, "sec": 1}
        secs = int(amount * multipliers[unit])
        label = f"{raw} {unit} timer"
        return Intent("set_timer", {"duration_seconds": secs, "label": label})

    # ── Alarm (digit) ─────────────────────────────────────────────────────────
    m = _ALARM_DIGIT.search(text)
    if m:
        h, mn, mer = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        h, mn = _apply_meridiem(h, mn, mer)
        return _alarm_intent(h, mn)

    # ── Alarm (word) ──────────────────────────────────────────────────────────
    m = _ALARM_WORD.search(text)
    if m:
        h = _HOUR_WORDS.get(m.group(1).lower(), 7)
        mn = _MINUTE_WORDS.get((m.group(2) or "").lower().strip(), 0)
        mer = (m.group(3) or "").lower()
        h, mn = _apply_meridiem(h, mn, mer)
        return _alarm_intent(h, mn)

    # ── Note ──────────────────────────────────────────────────────────────────
    m = _NOTE.search(text)
    if m:
        return Intent("add_note", {"content": m.group(1).strip()})

    return Intent("unknown")


def _apply_meridiem(h: int, mn: int, mer: str) -> tuple[int, int]:
    if mer == "pm" and h != 12: h += 12
    elif mer == "am" and h == 12: h = 0
    return h, mn


def _alarm_intent(h: int, mn: int) -> Intent:
    target = datetime.now().replace(hour=h % 24, minute=mn, second=0, microsecond=0)
    if target <= datetime.now():
        target += timedelta(days=1)
    return Intent("set_alarm", {"target_at": target.isoformat(), "label": f"Alarm at {h:02d}:{mn:02d}"})
