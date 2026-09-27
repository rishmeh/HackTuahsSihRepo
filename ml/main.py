"""
main.py — FastAPI application exposing the chat, vision, quiz, and flashcard endpoints.

Endpoints:
  POST /chat              — child-safe chat pipeline
  POST /chat/vision       — multimodal chat (text + images)
  POST /quiz              — quiz generation
  POST /flashcards        — flashcard deck generation
  GET  /health            — liveness check
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
from pathlib import Path
from typing import Annotated, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from chat.models import ChatRequest, ChatResponse, StudentProfile
from chat.pipeline import run_chat_pipeline
from chat.sanitizer import sanitize
from chat.complexity_judge import evaluate_pre_slm
from chat.safety_filter import apply_safety_filter
from chat.session_store import clear_session, get_history_from_db, history_as_messages
from flashcards.generator import generate_and_format_deck
from flashcards.models import FlashcardRequest
from quiz.generator import generate_and_format_quiz
from quiz.models import QuizRequest

# The face package lives at the repository root, outside ml/, so it can also be
# used standalone by the robot's camera loop. The server is normally started
# from inside ml/ ("uvicorn main:app"), which puts ml/ on sys.path but not its
# parent — so add the repository root before importing it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learner.routes import router as learner_router  # noqa: E402

from alarms.routes import router as alarms_router
from alarms.scheduler import start_scheduler
from weather.routes import router as weather_router
from notes.routes import router as notes_router
from persona_setup.router import router as persona_setup_router
from tasks_proxy import router as tasks_proxy_router
from ws_manager import manager
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Silence the every-5-second apscheduler executor heartbeat logs
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

import threading

_robot_state = {
    "face_state": "idle",
    "servo_state": "idle",
    "overlay_text": None,
    "overlay_duration": None,
    "revision": 0
}
_robot_telemetry = {}
_state_lock = threading.Lock()

def _set_robot_state(face: str = None, servo: str = None):
    with _state_lock:
        if face: _robot_state["face_state"] = face
        if servo: _robot_state["servo_state"] = servo
        _robot_state["revision"] += 1

import asyncio
async def _auto_idle(delay: float = 8.0):
    """Revert the robot state to idle after a delay so it can eventually sleep."""
    await asyncio.sleep(delay)
    _set_robot_state(face="idle", servo="idle")

app = FastAPI(title="KidBot ML API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(learner_router)
app.include_router(alarms_router)
app.include_router(weather_router)
app.include_router(notes_router)
app.include_router(persona_setup_router)
app.include_router(tasks_proxy_router)


@app.on_event("startup")
async def on_startup():
    start_scheduler()
    # Pre-load the SLM into Ollama memory so the first voice query has no
    # cold-start delay. Non-blocking — a warning is logged if Ollama is down.
    from chat.slm_client import warm_slm
    await warm_slm()
    logger.info("ML backend v3.0 started.")


# ---------------------------------------------------------------------------
# WebSocket — real-time event broadcast
# ---------------------------------------------------------------------------

@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled: %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal error. Please try again."})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
async def health():
    return {
        "status": "ok",
        "model": config.OLLAMA_MODEL,
    }


# ---------------------------------------------------------------------------
# Voice text-command (used by the dashboard Speak button — no wake word)
# ---------------------------------------------------------------------------

@app.post("/voice/text-command", tags=["Voice"])
async def voice_text_command(body: dict):
    """
    Three-layer intent resolution:
      1. Regex parser  — instant, no LLM needed
      2. LLM router    — fast Ollama call, structured token response
      3. Full LLM chat — fallback for open-ended questions
    """
    text = str(body.get("text", "")).strip()
    profile_id = int(body.get("profile_id", 0))
    if not text:
        return {"transcription": "", "response": "I didn't catch that."}

    from persona_setup import sessions as persona_sessions
    from voice_commands.intent import parse as _parse
    from voice_commands.dispatcher import dispatch as _dispatch
    from voice_commands.router import llm_route
    from quiz_sessions import sessions as _quiz_sessions

    profile_key = str(profile_id)

    # Quiz session intercepts all utterances while active
    if _quiz_sessions.is_active(profile_key):
        _intent = _parse(text)
        if _intent.name == "cancel_quiz":
            _quiz_sessions.cancel(profile_key)
            return {"transcription": text, "response": "Quiz cancelled. Come back anytime!", "quiz_active": False}
        reply, done = _quiz_sessions.answer(profile_key, text)
        return {"transcription": text, "response": reply, "quiz_active": not done}

    if persona_sessions.is_active(profile_key):
        if _parse(text).name == "cancel_persona_setup":
            persona_sessions.cancel(profile_key)
            return {
                "transcription": text,
                "response": "Okay, I cancelled persona setup. Your existing persona is unchanged.",
                "persona_setup_active": False,
                "persona_setup_complete": False,
            }
        _, reply, complete = persona_sessions.answer(profile_key, text, age=10)
        return {
            "transcription": text,
            "response": reply,
            "persona_setup_active": not complete,
            "persona_setup_complete": complete,
        }

    # Layer 1: regex
    intent = _parse(text)
    if intent.name == "start_persona_setup":
        return {
            "transcription": text,
            "response": persona_sessions.start(profile_key, age=10),
            "persona_setup_active": True,
            "persona_setup_complete": False,
        }
    if intent.name != "unknown":
        reply = _dispatch(intent, profile_id=profile_id)
        if reply:
            return {"transcription": text, "response": reply}

    # Layer 2: LLM router
    routed = await llm_route(text)
    if routed and routed.name != "unknown":
        reply = _dispatch(routed, profile_id=profile_id)
        if reply:
            return {"transcription": text, "response": reply}

    # Layer 3: full LLM chat
    _set_robot_state(face="thinking", servo="thinking")
    req = ChatRequest(
        query=text,
        student=StudentProfile(
            name="Voice User", age=10, grade="5th grade",
            personality_traits=["curious"], interests=[], language_level="intermediate",
        ),
        session_id=f"voice-browser-{profile_id}",
        student_id=profile_key,
    )
    chat_resp = await run_chat_pipeline(req)
    _set_robot_state(face="happy", servo="speaking")
    asyncio.create_task(_auto_idle())
    return {"transcription": text, "response": chat_resp.answer}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    logger.info("Chat | session=%s | age=%d", request.session_id, request.student.age)
    _set_robot_state(face="thinking", servo="thinking")
    resp = await run_chat_pipeline(request)
    _set_robot_state(face="happy", servo="speaking")
    asyncio.create_task(_auto_idle())
    return resp


@app.get("/chat/history/{session_id}", tags=["Chat"])
async def get_chat_history(session_id: str, limit: int = 50):
    return await get_history_from_db(session_id, limit)


@app.delete("/chat/session/{session_id}", tags=["Chat"])
async def clear_chat_session(session_id: str):
    clear_session(session_id)
    return {"cleared": session_id}


# ---------------------------------------------------------------------------
# Quiz & Flashcards
# ---------------------------------------------------------------------------

@app.post("/quiz", tags=["Quiz"])
async def quiz(request: QuizRequest):
    try:
        obj, fmt = await generate_and_format_quiz(request)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {**obj.model_dump(), "formatted": fmt}


@app.post("/flashcards", tags=["Flashcards"])
async def flashcards(request: FlashcardRequest):
    try:
        deck, fmt = await generate_and_format_deck(request)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {**deck.model_dump(), "formatted": fmt}


# ---------------------------------------------------------------------------
# Hardware Control API (for Pi peripheral daemon)
# ---------------------------------------------------------------------------


@app.get("/hardware/state")
async def hardware_get_state() -> dict:
    with _state_lock:
        return dict(_robot_state)


@app.post("/hardware/state/set")
async def hardware_set_state(request: Request) -> dict:
    body = await request.json()
    with _state_lock:
        _robot_telemetry.update(body)
    logger.info(
        "Hardware state | face=%s | servo=%s | student=%s",
        body.get("face_state"),
        body.get("servo_state"),
        body.get("student_id"),
    )
    return {"ack": True}


@app.get("/hardware/status")
async def hardware_status() -> dict:
    with _state_lock:
        return {"command": dict(_robot_state), "telemetry": dict(_robot_telemetry)}


@app.post("/hardware/control")
async def hardware_control(request: Request) -> dict:
    body = await request.json()
    with _state_lock:
        if "face_state" in body:
            _robot_state["face_state"] = body["face_state"]
        if "servo_state" in body:
            _robot_state["servo_state"] = body["servo_state"]
        if "overlay_text" in body:
            _robot_state["overlay_text"] = body["overlay_text"]
        if "overlay_duration" in body:
            _robot_state["overlay_duration"] = body["overlay_duration"]
        _robot_state["revision"] += 1
        return dict(_robot_state)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
