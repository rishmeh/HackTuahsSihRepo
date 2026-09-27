"""Full CRUD for sticky notes in the shared SQLite database.

Indexing side-effect:
  create_note  → extract_and_index()  (background task, non-blocking)
  update_note  → extract_and_index()  (re-indexes on content change)
  delete_note  → delete_index_for_note()
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel

from notes.extractor import ACCEPTED_EXTENSIONS, ExtractionError, extract_text
from notes.indexer import delete_index_for_note, extract_and_index

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notes", tags=["Notes"])
DB_PATH = Path(__file__).resolve().parent.parent.parent / "dashboard" / "data" / "tabletot.db"


class NoteCreate(BaseModel):
    owner_profile_id: int = 0
    title: str = "Untitled"
    content: str = ""
    tags: Optional[list[str]] = None
    color: str = "yellow"


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list[str]] = None
    is_pinned: Optional[bool] = None
    color: Optional[str] = None


async def _ensure():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ownerProfileId INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT 'Untitled',
                content TEXT NOT NULL DEFAULT '',
                tags TEXT,
                isPinned INTEGER NOT NULL DEFAULT 0,
                color TEXT NOT NULL DEFAULT 'yellow',
                createdAt INTEGER NOT NULL,
                updatedAt INTEGER NOT NULL
            )"""
        )
        await db.commit()


def _ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


@router.post("/")
async def create_note(body: NoteCreate, background_tasks: BackgroundTasks):
    await _ensure()
    now = _ms()
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO notes (ownerProfileId,title,content,tags,color,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?)",
            (body.owner_profile_id, body.title, body.content,
             json.dumps(body.tags) if body.tags else None, body.color, now, now),
        )
        await db.commit()
        note_id = c.lastrowid

    # Kick off concept extraction in the background so the HTTP response is instant
    if body.content and body.content.strip():
        background_tasks.add_task(
            extract_and_index, note_id, body.owner_profile_id, body.content, body.title
        )
        logger.info("Scheduled concept indexing for new note %d (profile %d).", note_id, body.owner_profile_id)

    return {"id": note_id, **body.model_dump()}


@router.get("/{profile_id}")
async def list_notes(profile_id: int):
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT * FROM notes WHERE ownerProfileId=? ORDER BY isPinned DESC,updatedAt DESC",
            (profile_id,),
        )).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
            result.append(d)
        return result


# ---------------------------------------------------------------------------
# File upload endpoint — PDF, image, or plain text → note + index
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_note_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile_id: int = 0,
    title: str = "",
    color: str = "yellow",
):
    """
    Upload a PDF, image, or .txt file and turn it into a queryable note.

    The file is read, text is extracted (PyMuPDF for PDFs, Tesseract for
    images if available), saved as a note in SQLite, and concept indexing
    is scheduled as a background task so the response is immediate.

    Returns the created note's ID and a preview of the extracted text.
    """
    # Validate extension
    filename = file.filename or "upload"
    from pathlib import Path as _Path
    suffix = _Path(filename).suffix.lower()
    if suffix not in ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix}'. "
                f"Accepted: {', '.join(sorted(ACCEPTED_EXTENSIONS))}"
            ),
        )

    # Read file bytes
    try:
        file_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Extract text
    try:
        extracted_text = extract_text(file_bytes, filename)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not extracted_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "No text could be extracted from this file. "
                "For image-based PDFs or photos of handwriting, ensure Tesseract OCR is installed."
            ),
        )

    # Use filename as title if none provided
    note_title = title.strip() or _Path(filename).stem.replace("_", " ").replace("-", " ").title()

    # Save as a note
    await _ensure()
    now = _ms()
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO notes (ownerProfileId, title, content, color, createdAt, updatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (profile_id, note_title, extracted_text, color, now, now),
        )
        await db.commit()
        note_id = c.lastrowid

    # Schedule concept indexing in the background
    background_tasks.add_task(extract_and_index, note_id, profile_id, extracted_text, note_title)
    logger.info(
        "File upload: note %d created for profile %d from '%s' (%d chars). Indexing scheduled.",
        note_id, profile_id, filename, len(extracted_text),
    )

    return {
        "id": note_id,
        "title": note_title,
        "profile_id": profile_id,
        "chars_extracted": len(extracted_text),
        "preview": extracted_text[:300],
        "status": "indexed_in_background",
    }


@router.put("/{note_id}")
async def update_note(note_id: int, body: NoteUpdate, background_tasks: BackgroundTasks):
    await _ensure()
    now = _ms()
    sets, vals = [], []
    if body.title is not None:    sets.append("title=?");    vals.append(body.title)
    if body.content is not None:  sets.append("content=?");  vals.append(body.content)
    if body.tags is not None:     sets.append("tags=?");     vals.append(json.dumps(body.tags))
    if body.is_pinned is not None: sets.append("isPinned=?"); vals.append(int(body.is_pinned))
    if body.color is not None:    sets.append("color=?");    vals.append(body.color)
    if not sets:
        raise HTTPException(400, "Nothing to update")
    sets.append("updatedAt=?"); vals.append(now); vals.append(note_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE notes SET {', '.join(sets)} WHERE id=?", vals)
        await db.commit()

    # Re-index if content or title changed
    if body.content is not None or body.title is not None:
        # Fetch the latest full note to get profile_id + merged content
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT ownerProfileId, title, content FROM notes WHERE id=?", (note_id,)
                )
            ).fetchone()
        if row and row["content"]:
            background_tasks.add_task(
                extract_and_index,
                note_id,
                row["ownerProfileId"],
                row["content"],
                row["title"] or "",
            )
            logger.info("Scheduled re-indexing for updated note %d.", note_id)

    return {"updated": note_id}


@router.delete("/{note_id}")
async def delete_note(note_id: int, background_tasks: BackgroundTasks):
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM notes WHERE id=?", (note_id,))
        await db.commit()
    background_tasks.add_task(delete_index_for_note, note_id)
    return {"deleted": note_id}


# ---------------------------------------------------------------------------
# Manual re-index endpoint (useful for notes that existed before indexing)
# ---------------------------------------------------------------------------

@router.post("/{note_id}/reindex")
async def reindex_note(note_id: int, background_tasks: BackgroundTasks):
    """Trigger concept re-extraction for an existing note."""
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (
            await db.execute(
                "SELECT ownerProfileId, title, content FROM notes WHERE id=?", (note_id,)
            )
        ).fetchone()
    if not row:
        raise HTTPException(404, "Note not found")
    if not row["content"]:
        return {"status": "skipped", "reason": "empty content"}

    background_tasks.add_task(
        extract_and_index,
        note_id,
        row["ownerProfileId"],
        row["content"],
        row["title"] or "",
    )
    return {"status": "reindex_scheduled", "note_id": note_id}


@router.post("/reindex-all/{profile_id}")
async def reindex_all_notes(profile_id: int, background_tasks: BackgroundTasks):
    """Re-index every note for a profile. Useful on first setup."""
    await _ensure()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (
            await db.execute(
                "SELECT id, title, content FROM notes WHERE ownerProfileId=?", (profile_id,)
            )
        ).fetchall()

    scheduled = 0
    for row in rows:
        if row["content"] and row["content"].strip():
            background_tasks.add_task(
                extract_and_index,
                row["id"],
                profile_id,
                row["content"],
                row["title"] or "",
            )
            scheduled += 1

    return {"status": "scheduled", "notes_scheduled": scheduled, "profile_id": profile_id}
