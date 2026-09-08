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
import cv2
import numpy as np
from pathlib import Path
from typing import Annotated, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from chat.models import ChatRequest, ChatResponse, StudentProfile
from chat.pipeline import run_chat_pipeline
from chat.sanitizer import sanitize
from chat.complexity_judge import evaluate_pre_slm
from chat.safety_filter import apply_safety_filter
from chat.session_store import clear_session, get_history_from_db, history_as_messages
from chat.vision_client import call_slm_vision
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
from vision.routes import router as vision_router  # noqa: E402
from vision.pipeline import VisionPipeline  # noqa: E402
from vision.factory import build_pipeline  # noqa: E402
from vision import config as vision_config  # noqa: E402
from robot_state import RobotState  # noqa: E402

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

app = FastAPI(title="KidBot ML API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vision_router)
app.include_router(learner_router)
app.include_router(alarms_router)
app.include_router(weather_router)
app.include_router(notes_router)
app.include_router(persona_setup_router)
app.include_router(tasks_proxy_router)


@app.on_event("startup")
async def on_startup():
    start_scheduler()
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
        "vision_model": config.OLLAMA_VISION_MODEL,
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
    return {"transcription": text, "response": chat_resp.answer}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    logger.info("Chat | session=%s | age=%d", request.session_id, request.student.age)
    return await run_chat_pipeline(request)


@app.get("/chat/history/{session_id}", tags=["Chat"])
async def get_chat_history(session_id: str, limit: int = 50):
    return await get_history_from_db(session_id, limit)


@app.delete("/chat/session/{session_id}", tags=["Chat"])
async def clear_chat_session(session_id: str):
    clear_session(session_id)
    return {"cleared": session_id}


@app.post("/chat/vision", response_model=ChatResponse, tags=["Chat"])
async def chat_vision(
    query: Annotated[str, Form(min_length=1, max_length=2000)],
    student: Annotated[str, Form()],
    images: Annotated[list[UploadFile], File()],
    session_id: Annotated[Optional[str], Form()] = None,
):
    try:
        sp = StudentProfile(**json.loads(student))
    except Exception as e:
        raise HTTPException(422, f"Invalid student JSON: {e}")
    if len(images) > 3:
        raise HTTPException(422, "Max 3 images")
    image_bytes = []
    for up in images:
        if not (up.content_type or "").startswith("image/"):
            raise HTTPException(422, f"Not an image: {up.filename}")
        image_bytes.append(await up.read())
    san = sanitize(query.strip())
    block, _, _ = evaluate_pre_slm(san.sanitized_text)
    if block:
        return ChatResponse(answer=config.FALLBACK_RESPONSE, source="fallback", session_id=session_id)
    history = history_as_messages(session_id) if session_id else []
    resp = await call_slm_vision(san.sanitized_text, image_bytes, sp, history)
    if resp is None:
        return ChatResponse(answer=config.FALLBACK_RESPONSE, source="fallback", session_id=session_id)
    fr = apply_safety_filter(resp.answer)
    return ChatResponse(
        answer=fr.text if fr.is_safe else config.FALLBACK_RESPONSE,
        source="slm_vision",
        session_id=session_id,
    )


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
# These endpoints let the Pi act as a pure hardware driver: it captures camera
# frames, drives two servos, and streams frames here for face processing.
# All computation stays on this machine (the laptop).

# Shared vision pipeline (loaded once, reused per frame)
_pipeline: Optional[VisionPipeline] = None
_robot_state = RobotState(
    confirm_frames=vision_config.FACE_CONFIRM_FRAMES,
    forget_frames=vision_config.FACE_FORGET_FRAMES,
)
_robot_events: queue.Queue[dict] = queue.Queue(maxsize=8)


def _put_latest(target: queue.Queue, item) -> None:
    """Bound latency by discarding the oldest item when a queue is full."""
    try:
        target.put_nowait(item)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(item)


def _get_pipeline() -> VisionPipeline:
    """Lazily load the vision pipeline once."""
    global _pipeline
    if _pipeline is None:
        try:
            _pipeline = build_pipeline()
            logger.info("Vision pipeline loaded for hardware stream")
        except Exception as exc:
            logger.error("Failed to build vision pipeline: %s", exc)
            raise HTTPException(status_code=503, detail="Vision pipeline not available")
    return _pipeline


@app.post("/hardware/process-frame")
async def hardware_process_frame(
    image: Annotated[UploadFile, File(description="JPEG frame from Pi camera")],
) -> dict:
    """
    Pi streams a camera frame here → laptop runs face detection + recognition.
    Returns the identified student_id (or null) + face metadata.
    """
    buffer = np.frombuffer(await image.read(), dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image")

    try:
        result = _get_pipeline().identify(frame)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Vision processing error: %s", exc)
        raise HTTPException(status_code=500, detail="Vision processing failed")

    faces = []
    if result.face:
        faces.append({
            "x": result.face.x,
            "y": result.face.y,
            "width": result.face.width,
            "height": result.face.height,
            "score": result.face.score,
        })

    command = _robot_state.observe_face(
        student_id=result.student_id,
        face_count=result.face_count,
        score=result.score,
    )
    event = command.pop("event")
    if event:
        _put_latest(
            _robot_events,
            {"event": event, "student_id": command.get("student_id")},
        )
    return {
        "face_count": result.face_count,
        "student_id": result.student_id,
        "score": round(result.score, 4),
        "faces": faces,
        "event": event,
        "command": command,
    }


@app.post("/hardware/greet")
async def hardware_greet(request: Request) -> dict:
    """Create a short greeting using the recognized student's laptop profile."""
    body = await request.json()
    student_id = str(body.get("student_id", "")).strip()
    if not student_id:
        raise HTTPException(status_code=400, detail="Missing 'student_id' field")
    stored = get_learner_store().get(student_id)
    age = stored.profile.age if stored is not None else 10
    chat_request = ChatRequest(
        query="Greet the recognized student warmly and ask whether they want to start studying. Use one short sentence.",
        student=StudentProfile(age=age),
        student_id=student_id,
        session_id=f"robot-{student_id}",
        situation="greeting",
    )
    response = await run_chat_pipeline(chat_request)
    return {"answer": response.answer, "student_id": student_id}


@app.get("/hardware/events")
async def hardware_event_next():
    """Return the next recognition event to the laptop voice worker."""
    try:
        return _robot_events.get_nowait()
    except queue.Empty:
        return Response(status_code=204)


@app.get("/hardware/state")
async def hardware_get_state() -> dict:
    """
    Pi polls this periodically to get current face/servo state.
    Returns the servo state the laptop wants the Pi to apply right now.
    """
    return _robot_state.command()


@app.post("/hardware/state/set")
async def hardware_set_state(request: Request) -> dict:
    """
    Pi reports its current state (optional — for debugging/monitoring).
    Also endpoint the brain can push state to (alternative to polling).
    """
    body = await request.json()
    _robot_state.update_telemetry(body)
    logger.info(
        "Hardware state | face=%s | servo=%s | student=%s",
        body.get("face_state"),
        body.get("servo_state"),
        body.get("student_id"),
    )
    return {"ack": True}


@app.get("/hardware/status")
async def hardware_status() -> dict:
    """Return laptop commands and the most recent Pi telemetry."""
    return _robot_state.status()


@app.post("/hardware/control")
async def hardware_control(request: Request) -> dict:
    """Issue an explicit robot-state/servo command from the laptop."""
    body = await request.json()
    try:
        return _robot_state.control(
            face_state=body.get("face_state"),
            servo_state=body.get("servo_state"),
            overlay_text=body.get("overlay_text"),
            overlay_duration=body.get("overlay_duration"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
