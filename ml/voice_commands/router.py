"""
voice_commands/router.py — LLM-based intent router.

Fallback layer between the regex parser and the full chat pipeline.
When the regex can't classify a query, this sends a tiny fast Ollama
call with a strict routing prompt that returns a single structured token.

Token reference:
  TIMER:300          → set_timer (seconds)
  ALARM:07:30        → set_alarm
  TASK:call mom      → create_task
  LIST:timers/alarms/notes/tasks
  NOTE:buy milk      → add_note
  TIME               → get_time
  WEATHER:Chennai    → get_weather
  CHAT               → unknown — fall through to full LLM
"""
from __future__ import annotations
import logging, re
from datetime import datetime, timedelta
from typing import Optional

import httpx
import config
from voice_commands.intent import Intent, _alarm_intent

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a voice command classifier. Your ONLY job is to output a single structured token.
No explanation. No punctuation. No extra words. Just the token.

Token formats:
  TIMER:<total_seconds>        countdown timer
  ALARM:<HH>:<MM>              alarm (24-h clock)
  TASK:<task title>            add a new to-do task
  LIST:timers                  show running timers
  LIST:alarms                  show set alarms
  LIST:notes                   show notes
  LIST:tasks                   show to-do list
  NOTE:<content>               save a note
  TIME                         current time
  WEATHER:<city>               weather query
  CHAT                         anything else

Examples (input → output):
  "set a timer for ten minutes"              → TIMER:600
  "set a timer for five minutes"             → TIMER:300
  "set a timer for half an hour"             → TIMER:1800
  "start a 2 hour timer"                     → TIMER:7200
  "wake me up at seven thirty"               → ALARM:7:30
  "set alarm at 9 am"                        → ALARM:9:00
  "add a task to call my mom"                → TASK:call my mom
  "do it for me set a to-do for calling mom" → TASK:call mom
  "remind me to buy groceries"               → TASK:buy groceries
  "write in my notes that I have to call my mom" → NOTE:I have to call my mom
  "note down that the meeting is at 3pm"     → NOTE:meeting at 3pm
  "what timers do I have"                    → LIST:timers
  "what alarms are set"                      → LIST:alarms
  "what are my notes"                        → LIST:notes
  "what's on my to-do list"                  → LIST:tasks
  "add a note buy milk"                      → NOTE:buy milk
  "what time is it"                          → TIME
  "what's the weather in Mumbai"             → WEATHER:Mumbai
  "explain gravity"                          → CHAT
  "help me with maths"                       → CHAT
"""


async def llm_route(text: str) -> Optional[Intent]:
    """
    Ask Ollama to classify the intent. Returns an Intent or None (CHAT).
    Fast: num_predict=30, temperature=0, no thinking mode.
    """
    try:
        payload = {
            "model": config.OLLAMA_MODEL,
            "system": _SYSTEM,
            "prompt": text,
            "stream": False,
            "options": {"num_predict": 30, "temperature": 0, "think": False},
        }
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(f"{config.OLLAMA_BASE_URL}/api/generate", json=payload)
        if not r.is_success:
            logger.warning("LLM router HTTP %d", r.status_code)
            return None
        token = r.json().get("response", "").strip()
        logger.info("LLM router: %r → %r", text[:60], token)
        return _parse_token(token)
    except Exception as exc:
        logger.warning("LLM router failed: %s", exc)
        return None


def _parse_token(token: str) -> Optional[Intent]:
    t = token.strip()

    # TIMER:<seconds>
    if m := re.match(r"TIMER:(\d+)", t, re.I):
        secs = int(m.group(1))
        mins, s = divmod(secs, 60)
        label = f"{mins} minute timer" if mins else f"{s} second timer"
        return Intent("set_timer", {"duration_seconds": secs, "label": label})

    # ALARM:<H>:<MM>
    if m := re.match(r"ALARM:(\d{1,2}):(\d{2})", t, re.I):
        return _alarm_intent(int(m.group(1)), int(m.group(2)))

    # TASK:<title>
    if m := re.match(r"TASK:(.+)", t, re.I):
        title = m.group(1).strip()
        if title:
            return Intent("create_task", {"title": title})

    # LIST:<type>
    if m := re.match(r"LIST:(timers?|alarms?|notes?|tasks?)", t, re.I):
        kind = m.group(1).lower()
        # normalise to plural
        if not kind.endswith("s"):
            kind += "s"
        return Intent(f"list_{kind}")

    # NOTE:<content>
    if m := re.match(r"NOTE:(.+)", t, re.I):
        content = m.group(1).strip()
        if content:
            return Intent("add_note", {"content": content})

    # TIME
    if re.match(r"TIME$", t, re.I):
        return Intent("get_time")

    # WEATHER:<city>
    if m := re.match(r"WEATHER:(.*)", t, re.I):
        return Intent("get_weather", {"location": m.group(1).strip()})

    # CHAT or unrecognised
    return None
