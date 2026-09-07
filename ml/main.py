"""
main.py — FastAPI ML backend v3.0.
New: timers, alarms, weather, notes, WebSocket events, chat history, voice text-command.
"""
from __future__ import annotations
import json, logging, sys
from pathlib import Path
from typing import Annotated, Optional

from fastapi import (
    FastAPI, File, Form, HTTPException, Request,
    UploadFile, WebSocket, WebSocketDisconnect,
)
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from learner.routes import router as learner_router  # noqa: E402
from vision.routes import router as vision_router    # noqa: E402

from alarms.routes import router as alarms_router
from alarms.scheduler import start_scheduler
from weather.routes import router as weather_router
from notes.routes import router as notes_router
from tasks_proxy import router as tasks_proxy_router
from ws_manager import manager
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
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
        "escalation_mode": config.ESCALATION_MODE,
    }


# ---------------------------------------------------------------------------
# Voice text-command (used by the dashboard Speak button — no wake word)
# ---------------------------------------------------------------------------

@app.post("/voice/text-command", tags=["Voice"])
async def voice_text_command(body: dict):
    """
    Accept pre-transcribed text from the browser Web Speech API,
    run intent dispatch, fall through to the LLM for unknown queries.
    """
    text = str(body.get("text", "")).strip()
    profile_id = int(body.get("profile_id", 0))
    if not text:
        return {"transcription": "", "response": "I didn't catch that."}

    from voice_commands.intent import parse as _parse
    from voice_commands.dispatcher import dispatch as _dispatch

    reply = _dispatch(_parse(text), profile_id=profile_id)
    if reply:
        return {"transcription": text, "response": reply}

    # Unknown intent — fall through to LLM
    req = ChatRequest(
        query=text,
        student=StudentProfile(
            name="Voice User", age=10, grade="5th grade",
            personality_traits=["curious"], interests=[], language_level="intermediate",
        ),
        session_id=f"voice-browser-{profile_id}",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
