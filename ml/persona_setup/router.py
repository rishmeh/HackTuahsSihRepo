"""
persona_setup/router.py — FastAPI endpoints for the conversational persona setup.

POST /persona/setup/start   → begin a setup session, returns first question
POST /persona/setup/answer  → submit one answer, returns next question or done
GET  /persona/setup/status  → is a session active for this profile?
GET  /persona/{profile_id}  → fetch the stored persona (for the dashboard)
DELETE /persona/{profile_id} → reset / clear a stored persona
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from learner.profile_store import ProfileStore
from learner.policy import derive_settings, default_settings
from learner import config as learner_config
from persona.prompt import build_persona_block
from persona_setup import sessions as setup_sessions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persona", tags=["Persona Setup"])


class StartRequest(BaseModel):
    profile_id: str
    age: int = 10


class AnswerRequest(BaseModel):
    profile_id: str
    answer: str
    age: int = 10


# ---------------------------------------------------------------------------
# Setup endpoints
# ---------------------------------------------------------------------------

@router.post("/setup/start")
async def start_setup(body: StartRequest):
    """Begin a persona setup session for a profile."""
    first_question = setup_sessions.start(body.profile_id, body.age)
    return {
        "started": True,
        "profile_id": body.profile_id,
        "reply": first_question,
        "complete": False,
    }


@router.post("/setup/answer")
async def submit_answer(body: AnswerRequest):
    """Submit one answer. Returns the next question or a completion message."""
    accepted, reply, complete = setup_sessions.answer(
        body.profile_id, body.answer, age=body.age
    )
    return {
        "accepted": accepted,
        "reply": reply,
        "complete": complete,
        "profile_id": body.profile_id,
    }


@router.post("/setup/cancel")
async def cancel_setup(body: StartRequest):
    """Discard an in-progress setup without changing the saved persona."""
    return {"cancelled": setup_sessions.cancel(body.profile_id), "profile_id": body.profile_id}


@router.get("/setup/status")
async def setup_status(profile_id: str):
    """Returns whether a persona setup session is currently active."""
    return {"active": setup_sessions.is_active(profile_id), "profile_id": profile_id}


# ---------------------------------------------------------------------------
# Stored persona endpoints
# ---------------------------------------------------------------------------

@router.get("/{profile_id}")
async def get_persona(profile_id: str):
    """Return the stored learner profile and derived TotSettings for a profile."""
    store = ProfileStore(learner_config.LEARNER_DB_PATH)
    stored = store.get(profile_id)
    if stored is None:
        settings = default_settings(age=10)
        return {
            "profile_id": profile_id,
            "has_persona": False,
            "settings": settings.model_dump(),
            "persona_block": build_persona_block(settings),
        }
    settings = derive_settings(stored.profile)
    return {
        "profile_id": profile_id,
        "has_persona": True,
        "updated_at": stored.updated_at,
        "settings": settings.model_dump(),
        "persona_block": build_persona_block(settings),
    }


@router.delete("/{profile_id}")
async def reset_persona(profile_id: str):
    """Delete a stored persona (resets to defaults)."""
    store = ProfileStore(learner_config.LEARNER_DB_PATH)
    removed = store.delete(profile_id)
    setup_sessions._sessions.pop(profile_id, None)
    return {"profile_id": profile_id, "deleted": removed}
