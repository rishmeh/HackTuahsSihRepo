"""
vision/routes.py — HTTP endpoints for face detection and recognition.

  POST   /vision/face/detect              is anyone there?
  POST   /vision/face/identify            who is there?
  POST   /vision/face/enroll              teach the robot a new face
  GET    /vision/face/students            who does it know?
  DELETE /vision/face/students/{id}       forget a student entirely

Kept in its own router rather than in main.py, which already carries the chat,
quiz and flashcard endpoints. The pipeline arrives through a FastAPI
dependency so tests can substitute one backed by a temporary database.

Frames arrive as uploaded image files rather than as a camera stream. The
robot's own loop calls the pipeline directly in-process; these endpoints exist
for enrolment from the parent dashboard and for testing from any browser.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from vision.models import (
    DetectionResponse,
    EnrollResponse,
    FaceBoxOut,
    IdentifyResponse,
)
from vision.pipeline import VisionPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision/face", tags=["Vision"])

# Enrolment sends a handful of frames; a cap keeps a malformed client from
# posting a hundred megabytes of images at the Pi.
MAX_ENROLL_FRAMES = 20


@lru_cache(maxsize=1)
def get_pipeline() -> VisionPipeline:
    """
    The process-wide vision pipeline.

    Cached because loading SFace costs a second or two and about 40 MB — far
    too much to repeat per request. Tests override this dependency rather than
    sharing the developer's real face database.
    """
    from vision.factory import build_pipeline

    return build_pipeline()


PipelineDep = Annotated[VisionPipeline, Depends(get_pipeline)]


def _decode(upload_bytes: bytes, filename: str) -> np.ndarray:
    """
    Turn uploaded bytes into a BGR frame.

    Raises:
        HTTPException: 422 if the bytes are not a decodable image.
    """
    buffer = np.frombuffer(upload_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(
            status_code=422,
            detail=f"{filename!r} could not be decoded as an image (JPEG or PNG expected)",
        )
    return frame


def _to_out(face) -> FaceBoxOut:
    return FaceBoxOut(
        x=face.x, y=face.y, width=face.width, height=face.height, score=face.score
    )


@router.post("/detect", response_model=DetectionResponse)
async def detect_faces(
    pipeline: PipelineDep,
    image: Annotated[UploadFile, File(description="A single JPEG or PNG frame")],
) -> DetectionResponse:
    """
    Find every face in one frame, nearest first.

    Detection only — this says a face is present, not whose it is. Use it for
    presence and framing checks, which are cheaper than recognition.
    """
    frame = _decode(await image.read(), image.filename or "image")
    faces = pipeline.detector.detect(frame)
    return DetectionResponse(
        face_count=len(faces), faces=[_to_out(f) for f in faces]
    )


@router.post("/identify", response_model=IdentifyResponse)
async def identify_face(
    pipeline: PipelineDep,
    image: Annotated[UploadFile, File(description="A single JPEG or PNG frame")],
) -> IdentifyResponse:
    """
    Identify the nearest face in one frame.

    ``student_id`` is null both when no face was found and when the face
    belongs to nobody enrolled — ``face_count`` tells the two apart. Callers
    should treat a null as "ask who this is", never as "close enough".
    """
    frame = _decode(await image.read(), image.filename or "image")
    result = pipeline.identify(frame)

    return IdentifyResponse(
        face_count=result.face_count,
        student_id=result.student_id,
        score=round(result.score, 4),
        face=_to_out(result.face) if result.face else None,
    )


@router.post("/enroll", response_model=EnrollResponse)
async def enroll_student(
    pipeline: PipelineDep,
    student_id: Annotated[str, Form(min_length=1, max_length=64)],
    images: Annotated[
        list[UploadFile],
        File(description="Several frames of one student, varying pose and lighting"),
    ],
) -> EnrollResponse:
    """
    Teach the robot a student's face.

    Send several frames taken across different poses and lighting — one frame
    enrols a student who is only recognised sitting exactly as they did during
    enrolment. Frames with no detectable face are skipped and counted.

    Only embeddings are stored. The uploaded images are decoded in memory and
    discarded when the request ends.
    """
    if len(images) > MAX_ENROLL_FRAMES:
        raise HTTPException(
            status_code=422,
            detail=f"at most {MAX_ENROLL_FRAMES} frames per enrolment request",
        )

    frames = [_decode(await img.read(), img.filename or "image") for img in images]

    try:
        result = pipeline.enroll(student_id, frames)
    except ValueError as exc:
        # Not a server fault — the frames simply had nobody in them.
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Enrolled %r: +%d embeddings (%d total, %d frames rejected)",
        result.student_id,
        result.embeddings_added,
        result.embeddings_total,
        result.frames_rejected,
    )

    return EnrollResponse(
        student_id=result.student_id,
        embeddings_added=result.embeddings_added,
        embeddings_total=result.embeddings_total,
        frames_rejected=result.frames_rejected,
    )


@router.get("/students")
async def list_students(pipeline: PipelineDep) -> dict:
    """Every student the robot can currently recognise."""
    return {"students": pipeline.enrolled_students}


@router.delete("/students/{student_id}")
async def delete_student(pipeline: PipelineDep, student_id: str) -> dict:
    """
    Erase every embedding for a student.

    This is the right-to-be-forgotten path: after it returns, the robot cannot
    recognise that student until they enrol again.
    """
    removed = pipeline.store.delete_student(student_id)
    pipeline.reload_gallery()
    logger.info("Erased %d embedding(s) for %r", removed, student_id)
    return {"student_id": student_id, "embeddings_removed": removed}
