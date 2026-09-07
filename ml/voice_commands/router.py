"""
voice_commands/router.py — LLM-based intent router.

Fallback layer between the regex parser and the full chat pipeline.
When the regex can't parse a query (e.g. "set a timer for ten minutes"
typed as words, or unusual phrasing), this sends a tiny fast Ollama
call with a strict system prompt that returns a structured token:

  TIMER:300          → set_timer (300 seconds)
  ALARM:07:30        → set_alarm at 07:30
  LIST:timers        → list_timers
  LIST:alarms        → list_alarms
  LIST:notes         → list_notes
  LIST:tasks         → list_tasks
  NOTE:buy milk      → add_note
  TIME               → get_time
  WEATHER:Chennai    → get_weather
  CHAT               → unknown (fall through to full LLM)

The call uses num_predict=30 and temperature=0 so it's very fast (~0.3 s
on a local Ollama instance) and deterministic.
"""
from __future__ import annotations
import logging, re
from datetime import datetime, timedelta
from typing import Optional

import httpx
import config
from voice_commands.intent import Intent, _alarm_intent

logger = logging.getLogger(__name__)

_SYSTEM = """You are a voice command classifier. Classify the user's command into exactly one token. Reply with ONLY the token — no explanation, no punctuation, nothing else.

Token formats:
  TIMER:<total_seconds>          user wants to set a countdown timer
  ALARM:<HH>:<MM>                user wants to set an alarm (24-h clock)
  LIST:timers                    user wants to know what timers are running
  LIST:alarms                    user wants to know what alarms are set
  LIST:notes                     user wants to hear their notes
  LIST:tasks                     user wants to hear their to-do list
  NOTE:<content>                 user wants to save a note
  TIME                           user is asking for the current time
  WEATHER:<city>                 user is asking about the weather
  CHAT                           anything else

Examples:
  "set a timer for ten minutes"  → TIMER:600
  "set a timer for five minutes" → TIMER:300
  "set a timer for half an hour" → TIMER:1800
  "wake me up at seven thirty"   → ALARM:7:30
  "set alarm at 9 am"            → ALARM:9:00
  "what timers do I have"        → LIST:timers
  "what's on my to-do list"      → LIST:tasks
  "add a note: buy milk"         → NOTE:buy milk
  "what time is it"              → TIME
  "what's the weather in Mumbai" → WEATHER:Mumbai
  "explain gravity"              → CHAT
"""


async def llm_route(text: str) -> Optional[Intent]:
    """
    Ask Ollama to classify the intent. Returns an Intent or None (CHAT).
    Designed to be fast: num_predict=30, temperature=0, no thinking.
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
            logger.warning("LLM router HTTP error %d", r.status_code)
            return None
        token = r.json().get("response", "").strip()
        logger.info("LLM router token: %r", token)
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
        h, mn = int(m.group(1)), int(m.group(2))
        return _alarm_intent(h, mn)

    # LIST:<type>
    if m := re.match(r"LIST:(timers?|alarms?|notes?|tasks?)", t, re.I):
        kind = m.group(1).lower().rstrip("s") + "s"  # normalise to plural
        return Intent(f"list_{kind}")

    # NOTE:<content>
    if m := re.match(r"NOTE:(.+)", t, re.I):
        return Intent("add_note", {"content": m.group(1).strip()})

    # TIME
    if re.match(r"TIME$", t, re.I):
        return Intent("get_time")

    # WEATHER:<city>
    if m := re.match(r"WEATHER:(.*)", t, re.I):
        return Intent("get_weather", {"location": m.group(1).strip()})

    # CHAT or unrecognised
    return None
