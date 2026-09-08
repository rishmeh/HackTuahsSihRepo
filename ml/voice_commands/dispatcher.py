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
            r = requests.get(f"{ML_BASE}/weather", params={"location": loc}, timeout=20)
            if r.ok:
                d = r.json()
                desc = d.get("weather", [{}])[0].get("description", "")
                temp = d.get("main", {}).get("temp", "?")
                hum  = d.get("main", {}).get("humidity", "?")
                return f"In {loc.title()}, it's {temp} degrees Celsius with {desc}. Humidity is {hum} percent."
            elif r.status_code == 503:
                return ("Weather isn't available right now because no OpenWeatherMap API key "
                        "is configured. Add OPENWEATHERMAP_API_KEY to ml/.env to enable it.")
            elif r.status_code == 404:
                return f"I couldn't find weather data for {loc}. Try a different city name."
            else:
                logger.warning("Weather endpoint returned %d: %s", r.status_code, r.text[:200])
        except requests.exceptions.Timeout:
            logger.warning("Weather request timed out for location: %s", loc)
            return "The weather service is taking too long to respond. Please try again shortly."
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

    # ── Quiz creation ──────────────────────────────────────────────────────────
    if n == "create_quiz":
        topic = intent.params.get("topic", "").strip()
        if not topic:
            return "What topic should the quiz be about?"
        try:
            import asyncio as _asyncio
            from quiz.generator import generate_and_format_quiz
            from quiz.models import QuizRequest, QuizStudentProfile
            import json

            req = QuizRequest(
                subject=topic,
                num_questions=5,
                student=QuizStudentProfile(age=10, covered_topics=[topic]),
            )
            quiz_obj, _ = _asyncio.run(generate_and_format_quiz(req))
            questions_json = json.dumps([q.model_dump() for q in quiz_obj.questions])

            # Save to dashboard DB via REST
            DASHBOARD_URL = "http://localhost:3000"
            save_r = requests.post(
                f"{DASHBOARD_URL}/api/quizzes",
                json={
                    "ownerProfileId": profile_id,
                    "topic": topic,
                    "questions": questions_json,
                    "totalQuestions": quiz_obj.num_questions,
                },
                timeout=10,
            )
            if save_r.ok:
                return (
                    f"Done! I've created a {quiz_obj.num_questions}-question quiz on {topic} "
                    "and saved it to your dashboard. Say 'take a quiz on "
                    + topic + "' to start it!"
                )
            return f"I generated a quiz on {topic} but couldn't save it to your dashboard right now."
        except Exception as e:
            logger.warning("Quiz creation failed: %s", e)
        return "Sorry, I couldn't create a quiz right now. Please try again."

    # ── Flashcard creation ─────────────────────────────────────────────────────
    if n == "create_flashcards":
        topic = intent.params.get("topic", "").strip()
        if not topic:
            return "What topic should the flashcards cover?"
        try:
            import asyncio as _asyncio
            from flashcards.generator import generate_and_format_deck
            from flashcards.models import FlashcardRequest, FlashcardStudentProfile
            import json

            req = FlashcardRequest(
                subject=topic,
                num_cards=8,
                student=FlashcardStudentProfile(age=10, covered_topics=[topic]),
            )
            deck_obj, _ = _asyncio.run(generate_and_format_deck(req))
            cards_json = json.dumps([c.model_dump() for c in deck_obj.cards])

            DASHBOARD_URL = "http://localhost:3000"
            save_r = requests.post(
                f"{DASHBOARD_URL}/api/flashcards",
                json={
                    "ownerProfileId": profile_id,
                    "topic": topic,
                    "cards": cards_json,
                    "totalCards": deck_obj.num_cards,
                },
                timeout=10,
            )
            if save_r.ok:
                return (
                    f"Done! I've made {deck_obj.num_cards} flashcards on {topic} "
                    "and saved them to your dashboard. Open the Flashcards widget to study!"
                )
            return f"I generated flashcards on {topic} but couldn't save them to your dashboard."
        except Exception as e:
            logger.warning("Flashcard creation failed: %s", e)
        return "Sorry, I couldn't create flashcards right now. Please try again."

    # ── Take quiz (interactive voice quiz session) ─────────────────────────────
    if n == "take_quiz":
        topic = intent.params.get("topic", "").strip()
        if not topic:
            return "What topic would you like to be quizzed on?"
        try:
            import asyncio as _asyncio
            from quiz.generator import generate_and_format_quiz
            from quiz.models import QuizRequest, QuizStudentProfile
            from quiz_sessions import sessions as _quiz_sessions

            req = QuizRequest(
                subject=topic,
                num_questions=3,
                student=QuizStudentProfile(age=10, covered_topics=[topic]),
            )
            quiz_obj, _ = _asyncio.run(generate_and_format_quiz(req))
            questions = [q.model_dump() for q in quiz_obj.questions]
            return _quiz_sessions.start(str(profile_id), topic, questions)
        except Exception as e:
            logger.warning("Take quiz failed: %s", e)
        return "Sorry, I couldn't start a quiz right now."

    # ── Cancel quiz ────────────────────────────────────────────────────────────
    if n == "cancel_quiz":
        from quiz_sessions import sessions as _quiz_sessions
        _quiz_sessions.cancel(str(profile_id))
        return "Quiz cancelled. No worries — come back when you're ready!"

    return None  # unknown — fall through to LLM
