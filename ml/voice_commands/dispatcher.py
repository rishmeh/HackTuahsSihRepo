"""Dispatch a parsed Intent to the backend and return a spoken reply (or None for LLM)."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from voice_commands.intent import Intent

logger = logging.getLogger(__name__)
ML_BASE = "http://127.0.0.1:8000"


def dispatch(intent: Intent, profile_id: int = 0) -> Optional[str]:
    """Return a spoken string, or None to fall through to the LLM."""
    n = intent.name

    if n == "get_time":
        return f"The current time is {datetime.now().strftime('%I:%M %p')}."

    if n == "get_weather":
        loc = intent.params.get("location") or "your city"
        try:
            r = requests.get(f"{ML_BASE}/weather", params={"location": loc}, timeout=10)
            if r.ok:
                d = r.json()
                desc = d.get("weather", [{}])[0].get("description", "")
                temp = d.get("main", {}).get("temp", "?")
                hum  = d.get("main", {}).get("humidity", "?")
                return f"In {loc.title()}, it's {temp} degrees Celsius with {desc}. Humidity is {hum} percent."
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
        return "Sorry, I couldn't fetch the weather right now."

    if n == "set_timer":
        secs, label = intent.params["duration_seconds"], intent.params["label"]
        try:
            r = requests.post(f"{ML_BASE}/alarms/timers",
                              json={"label": label, "duration_seconds": secs, "profile_id": profile_id},
                              timeout=5)
            if r.ok:
                tid = r.json().get("id")
                requests.post(f"{ML_BASE}/alarms/timers/{tid}/start", timeout=5)
                m, s = divmod(secs, 60)
                if m and s:
                    dur = f"{m} minute{'s' if m > 1 else ''} and {s} second{'s' if s > 1 else ''}"
                elif m:
                    dur = f"{m} minute{'s' if m > 1 else ''}"
                else:
                    dur = f"{s} second{'s' if s > 1 else ''}"
                return f"Timer set for {dur}. Starting now!"
        except Exception as e:
            logger.warning("Timer creation failed: %s", e)
        return "Sorry, I couldn't set the timer."

    if n == "set_alarm":
        label, target = intent.params["label"], intent.params["target_at"]
        try:
            r = requests.post(f"{ML_BASE}/alarms/",
                              json={"label": label, "target_at": target, "profile_id": profile_id},
                              timeout=5)
            if r.ok:
                return f"{label} has been set."
        except Exception as e:
            logger.warning("Alarm creation failed: %s", e)
        return "Sorry, I couldn't set the alarm."

    if n == "create_task":
        title = intent.params.get("title", "").strip()
        if not title:
            return "What should I call the task?"
        try:
            r = requests.post(
                f"{ML_BASE}/tasks_proxy/{profile_id}",
                json={"title": title},
                timeout=5,
            )
            if r.ok:
                return f"Done! I've added '{title}' to your to-do list."
        except Exception as e:
            logger.warning("Create task failed: %s", e)
        return "Sorry, I couldn't add the task right now."

    if n == "add_note":
        content = intent.params["content"]
        try:
            r = requests.post(f"{ML_BASE}/notes/",
                              json={"owner_profile_id": profile_id, "content": content, "title": content[:50]},
                              timeout=5)
            if r.ok:
                return "Got it, I've saved that note for you."
        except Exception as e:
            logger.warning("Note creation failed: %s", e)
        return "Sorry, I couldn't save the note."

    if n == "list_timers":
        try:
            r = requests.get(f"{ML_BASE}/alarms/timers", timeout=5)
            if r.ok:
                timers = r.json()
                if not timers: return "You have no active timers right now."
                parts = []
                for t in timers[:3]:
                    tl, st = t.get("label", "Timer"), t.get("status", "")
                    tgt = t.get("targetAt") or t.get("target_at")
                    if st == "running" and tgt:
                        rem = max(0, (tgt - int(datetime.now(timezone.utc).timestamp() * 1000)) // 1000)
                        m, s = divmod(rem, 60)
                        parts.append(f"{tl}: {m}m {s}s remaining" if m else f"{tl}: {s} seconds remaining")
                    elif st == "paused":
                        rem = t.get("remainingSeconds", 0) or 0
                        m, s = divmod(rem, 60)
                        parts.append(f"{tl}: paused, {m}m {s}s left")
                    else:
                        parts.append(f"{tl} ({st})")
                count = len(timers)
                return f"You have {count} timer{'s' if count > 1 else ''}. " + ". ".join(parts) + "."
        except Exception as e:
            logger.warning("List timers failed: %s", e)
        return "Sorry, I couldn't fetch your timers."

    if n == "list_alarms":
        try:
            r = requests.get(f"{ML_BASE}/alarms/", timeout=5)
            if r.ok:
                alarms = r.json()
                if not alarms: return "You have no active alarms set."
                parts = []
                for a in alarms[:3]:
                    tgt = a.get("targetAt") or a.get("target_at")
                    t_str = datetime.fromtimestamp(tgt / 1000).strftime("%I:%M %p") if tgt else ""
                    parts.append(f"{a.get('label', 'Alarm')} at {t_str}")
                count = len(alarms)
                return f"You have {count} alarm{'s' if count > 1 else ''}. " + ". ".join(parts) + "."
        except Exception as e:
            logger.warning("List alarms failed: %s", e)
        return "Sorry, I couldn't fetch your alarms."

    if n == "list_notes":
        try:
            r = requests.get(f"{ML_BASE}/notes/{profile_id}", timeout=5)
            if r.ok:
                notes = r.json()
                if not notes: return "You don't have any notes yet."
                titles = [note.get("title", "Untitled") for note in notes[:3]]
                count = len(notes)
                if count == 1:
                    return f"You have one note titled: {titles[0]}."
                return (f"You have {count} notes. "
                        f"The first {'three are' if count >= 3 else 'few are'}: "
                        + ", ".join(titles) + ".")
        except Exception as e:
            logger.warning("List notes failed: %s", e)
        return "Sorry, I couldn't fetch your notes."

    if n == "list_tasks":
        try:
            r = requests.get(f"{ML_BASE}/tasks_proxy/{profile_id}", timeout=5)
            if r.ok:
                tasks = [t for t in r.json() if not t.get("done")]
                if not tasks: return "You have no pending tasks. Great job!"
                titles = [t.get("title", "Untitled") for t in tasks[:3]]
                count = len(tasks)
                if count == 1:
                    return f"You have one pending task: {titles[0]}."
                return (f"You have {count} pending tasks. "
                        f"The first {'three are' if count >= 3 else 'few are'}: "
                        + ", ".join(titles) + ".")
        except Exception as e:
            logger.warning("List tasks failed: %s", e)
        return "Sorry, I couldn't fetch your tasks."

    return None  # unknown — fall through to LLM
