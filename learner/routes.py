"""
learner/routes.py — HTTP endpoints for the onboarding questionnaire.

  GET    /learner/questionnaire            the 10 scenes, for the student app
  POST   /learner/{id}/answers             submit answers → profile + settings
  GET    /learner/{id}/profile             the stored profile
  GET    /learner/{id}/settings            what Tot should do for this student
  GET    /learner/students                 who has a profile
  DELETE /learner/{id}                     erase a student's profile

The app calls the first two. Tot's own chat and voice layers call /settings.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from learner.models import AnswerSubmission, LearnerProfile, ProfileResponse, TotSettings
from learner.policy import derive_settings
from learner.profile_store import ProfileStore
from learner.questionnaire import Questionnaire, load_questionnaire
from learner.scoring import score_answers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learner", tags=["Learner"])


@lru_cache(maxsize=1)
def get_store() -> ProfileStore:
    from learner import config

    return ProfileStore(config.LEARNER_DB_PATH)


@lru_cache(maxsize=1)
def get_questionnaire() -> Questionnaire:
    return load_questionnaire()


StoreDep = Annotated[ProfileStore, Depends(get_store)]
QuestionnaireDep = Annotated[Questionnaire, Depends(get_questionnaire)]


class SubmissionResponse(BaseModel):
    student_id: str
    profile: LearnerProfile
    settings: TotSettings


@router.get("/questionnaire")
async def questionnaire(q: QuestionnaireDep) -> dict:
    """
    The onboarding questionnaire, as the student app should display it.

    Contains scene text and options only — never what an answer reveals.
    """
    return q.public_view()


@router.get("/students")
async def list_students(store: StoreDep) -> dict:
    return {"students": store.list_students()}


@router.post("/{student_id}/answers", response_model=SubmissionResponse)
async def submit_answers(
    student_id: str,
    submission: AnswerSubmission,
    store: StoreDep,
    q: QuestionnaireDep,
) -> SubmissionResponse:
    """
    Score a student's answers, store the profile, and return what Tot will do.

    Skipped scenes may be omitted; they score as "unknown", never as a guess.
    Submitting again replaces the previous profile.
    """
    try:
        profile = score_answers(submission.answers, age=submission.age, questionnaire=q)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    store.save(student_id, profile)
    settings = derive_settings(profile)

    logger.info(
        "Profile for %r: %d/10 answered | format=%s persona=%s sarcasm=%s",
        student_id, profile.answered, settings.response_format,
        settings.persona_mode, settings.sarcasm_allowed,
    )
    return SubmissionResponse(student_id=student_id, profile=profile, settings=settings)


@router.get("/{student_id}/profile", response_model=ProfileResponse)
async def get_profile(student_id: str, store: StoreDep) -> ProfileResponse:
    stored = store.get(student_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"no profile for student {student_id!r}")
    return ProfileResponse(
        student_id=student_id, profile=stored.profile, updated_at=stored.updated_at
    )


@router.get("/{student_id}/settings", response_model=TotSettings)
async def get_settings(student_id: str, store: StoreDep) -> TotSettings:
    """
    What Tot should do for this student right now.

    Derived fresh from the stored profile on every call, so a change to the
    policy rules takes effect without re-running the questionnaire.
    """
    stored = store.get(student_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"no profile for student {student_id!r}")
    return derive_settings(stored.profile)


@router.delete("/{student_id}")
async def delete_profile(student_id: str, store: StoreDep) -> dict:
    """Erase everything the questionnaire recorded about a student."""
    return {"student_id": student_id, "deleted": store.delete(student_id)}
