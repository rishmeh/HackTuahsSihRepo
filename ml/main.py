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
import sys
from typing import Annotated, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from chat.models import ChatRequest, ChatResponse, StudentProfile
from chat.pipeline import run_chat_pipeline
from chat.sanitizer import sanitize
from chat.complexity_judge import evaluate_pre_slm
from chat.safety_filter import apply_safety_filter
from chat.session_store import clear_session, history_as_messages
from chat.vision_client import call_slm_vision
from flashcards.generator import generate_and_format_deck
from flashcards.models import FlashcardDeck, FlashcardRequest
from quiz.generator import generate_and_format_quiz
from quiz.models import Quiz, QuizRequest
from vision.routes import router as vision_router

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="KidBot ML API",
    description=(
        "Child-safe chat pipeline (local SLM → thinking-mode or OpenRouter escalation), "
        "multimodal vision chat, age-appropriate quiz generator, flashcard generator, "
        "and on-device face detection / recognition."
    ),
    version="2.0.0",
)

# Face detection and recognition (YuNet + SFace). The models load lazily on the
# first request, so the server still starts if they have not been downloaded yet.
app.include_router(vision_router)


# ---------------------------------------------------------------------------
# Global exception handler — never leak internal errors to callers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "model": config.OLLAMA_MODEL,
        "vision_model": config.OLLAMA_VISION_MODEL,
        "escalation_mode": config.ESCALATION_MODE,
    }


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Submit a child's query along with their student profile.

    The pipeline will:
    1. Sanitize PII from the query.
    2. Ask the local SLM (think=False — fast path).
    3. On low confidence, escalate based on ESCALATION_MODE:
       - "model_thinking": retry SLM with think=True
       - "openrouter": forward to OpenRouter (no PII sent)
    4. Apply safety filtering to all responses.
    """
    logger.info("Chat request received | session=%s | age=%d", request.session_id, request.student.age)
    response = await run_chat_pipeline(request)
    logger.info(
        "Chat response | source=%s | escalated=%s | thinking=%s",
        response.source, response.escalated, response.thinking,
    )
    return response


@app.delete("/chat/session/{session_id}", tags=["Chat"])
async def clear_chat_session(session_id: str) -> dict:
    """
    Clear the conversation history for a given session.
    Call this when a student starts a new topic or logs out.
    """
    clear_session(session_id)
    logger.info("Session %s cleared via API.", session_id)
    return {"cleared": session_id}


# ---------------------------------------------------------------------------
# Vision chat endpoint
# ---------------------------------------------------------------------------

@app.post(
    "/chat/vision",
    response_model=ChatResponse,
    tags=["Chat"],
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["query", "student", "images"],
                        "properties": {
                            "query": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 2000,
                                "description": "The child's text question.",
                                "example": "What animal is shown in this picture?",
                            },
                            "student": {
                                "type": "string",
                                "description": 'StudentProfile as a JSON string. Example: {"age":10,"grade":"5th","covered_topics":["animals"]}',
                                "example": '{"age": 10, "grade": "5th", "covered_topics": ["animals"]}',
                            },
                            "images": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "description": "One to 3 image files (JPEG or PNG). Click 'Add item' to attach multiple files.",
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Optional session identifier for conversation history.",
                            },
                        },
                    }
                }
            }
        }
    },
)
async def chat_vision(
    query: Annotated[str, Form(min_length=1, max_length=2000)],
    student: Annotated[str, Form(description="StudentProfile as a JSON string")],
    images: Annotated[list[UploadFile], File(description="Up to 3 image files (JPEG/PNG)")],
    session_id: Annotated[Optional[str], Form()] = None,
) -> ChatResponse:
    """
    Submit a child's question along with up to 3 images (JPEG/PNG).

    Accepts `multipart/form-data` with:
    - `query`      — the text question
    - `student`    — JSON-encoded StudentProfile
    - `images`     — one or more image files
    - `session_id` — optional session identifier

    The vision path uses the local SLM's multimodal capability (think=False).
    Safety filtering is applied to all responses.
    """
    # Parse student profile
    try:
        student_data = json.loads(student)
        student_profile = StudentProfile(**student_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid student JSON: {exc}")

    if len(images) > 3:
        raise HTTPException(status_code=422, detail="A maximum of 3 images are allowed per request.")

    logger.info(
        "Vision chat request | session=%s | age=%d | images=%d",
        session_id, student_profile.age, len(images),
    )

    # Read image bytes
    image_bytes: list[bytes] = []
    for upload in images:
        content_type = upload.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=422,
                detail=f"File '{upload.filename}' is not a recognised image type.",
            )
        image_bytes.append(await upload.read())

    # Sanitize text query + pre-SLM gate
    sanitization = sanitize(query.strip())
    sanitized_query = sanitization.sanitized_text
    block_escalation, force_escalation, _ = evaluate_pre_slm(sanitized_query)

    if block_escalation:
        return ChatResponse(
            answer=config.FALLBACK_RESPONSE,
            source="fallback",
            session_id=session_id,
        )

    history = history_as_messages(session_id) if session_id else []

    slm_response = await call_slm_vision(sanitized_query, image_bytes, student_profile, history)

    if slm_response is None:
        logger.error("Vision SLM returned None.")
        return ChatResponse(
            answer=config.FALLBACK_RESPONSE,
            source="fallback",
            session_id=session_id,
        )

    filter_result = apply_safety_filter(slm_response.answer)
    answer_text = filter_result.text if filter_result.is_safe else config.FALLBACK_RESPONSE

    logger.info("Vision response | confidence=%.2f | safe=%s", slm_response.confidence, filter_result.is_safe)
    return ChatResponse(
        answer=answer_text,
        source="slm_vision",
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Quiz endpoint
# ---------------------------------------------------------------------------

class QuizResponse(Quiz):
    formatted: str = ""


@app.post("/quiz", tags=["Quiz"])
async def quiz(request: QuizRequest) -> dict:
    """
    Generate a 5–10 question quiz based on the student profile and subject.

    Returns the full structured quiz (JSON) plus a formatted text version.
    """
    logger.info(
        "Quiz request received | subject=%r | age=%d | questions=%d",
        request.subject,
        request.student.age,
        request.num_questions,
    )
    try:
        quiz_obj, formatted = await generate_and_format_quiz(request)
    except RuntimeError as exc:
        logger.error("Quiz generation failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        **quiz_obj.model_dump(),
        "formatted": formatted,
    }


# ---------------------------------------------------------------------------
# Flashcards endpoint
# ---------------------------------------------------------------------------

@app.post("/flashcards", tags=["Flashcards"])
async def flashcards(request: FlashcardRequest) -> dict:
    """
    Generate a deck of study flashcards based on topics the student has covered.

    Returns the full structured deck (JSON) plus a formatted text version.
    """
    logger.info(
        "Flashcard request | subject=%r | age=%d | cards=%d | topics=%s",
        request.subject,
        request.student.age,
        request.num_cards,
        request.student.covered_topics,
    )
    try:
        deck, formatted = await generate_and_format_deck(request)
    except RuntimeError as exc:
        logger.error("Flashcard generation failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        **deck.model_dump(),
        "formatted": formatted,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
