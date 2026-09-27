"""
notes/extractor.py — Extract plain text from uploaded files.

Supported formats:
  PDF  — PyMuPDF (fitz). Handles both selectable-text and image-based PDFs.
         For image-based pages, falls back to page-level rasterisation so the
         content is at least partially recoverable (full OCR via Tesseract is
         optional and only used when available).
  Images (PNG, JPG, JPEG, WEBP, BMP) — PyMuPDF can open these directly too.
  Plain text (.txt) — read as-is.

PyMuPDF is already in requirements.txt (pymupdf==1.28.0), so no new deps.
Tesseract / pytesseract are optional — used when installed, skipped otherwise.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Tesseract import — graceful degradation if not installed
# ---------------------------------------------------------------------------
try:
    import pytesseract
    from PIL import Image
    import io
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False
    logger.info(
        "pytesseract / pillow not available — image-only PDF pages will be skipped. "
        "Install pytesseract + tesseract-ocr for full OCR support."
    )

# ---------------------------------------------------------------------------
# PyMuPDF import
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False
    logger.error(
        "PyMuPDF (fitz) is not installed. PDF extraction will not work. "
        "Run: pip install pymupdf"
    )

# Accepted MIME types → handler method
ACCEPTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
    "text/plain",
}

ACCEPTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".txt"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ExtractionError(ValueError):
    """Raised when a file cannot be processed."""


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Extract plain text from uploaded file bytes.

    Args:
        file_bytes: Raw bytes of the uploaded file.
        filename:   Original filename (used to determine format).

    Returns:
        Extracted text string (may be empty for blank/image-only files).

    Raises:
        ExtractionError: If the file format is unsupported or corrupted.
    """
    suffix = Path(filename).suffix.lower()

    if suffix == ".txt":
        return _extract_txt(file_bytes)
    elif suffix == ".pdf":
        return _extract_pdf(file_bytes, filename)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return _extract_image(file_bytes, filename)
    else:
        raise ExtractionError(
            f"Unsupported file type '{suffix}'. "
            f"Accepted: {', '.join(sorted(ACCEPTED_EXTENSIONS))}"
        )


# ---------------------------------------------------------------------------
# Format handlers
# ---------------------------------------------------------------------------

def _extract_txt(file_bytes: bytes) -> str:
    """Decode plain text, trying UTF-8 then latin-1."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="replace")


def _extract_pdf(file_bytes: bytes, filename: str) -> str:
    """
    Extract text from a PDF using PyMuPDF.

    Strategy per page:
      1. Try get_text("text") — works for selectable/typed PDFs instantly.
      2. If a page yields no text (scanned/image PDF), rasterise to image
         and run Tesseract OCR if available.
    """
    if not _FITZ_AVAILABLE:
        raise ExtractionError("PyMuPDF is not installed — cannot extract PDF text.")

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(f"Could not open PDF '{filename}': {exc}") from exc

    pages_text: list[str] = []
    ocr_pages = 0

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()

        if text:
            pages_text.append(text)
        elif _TESSERACT_AVAILABLE:
            # Image-only page — rasterise at 150 DPI and OCR
            try:
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                ocr_text = pytesseract.image_to_string(img).strip()
                if ocr_text:
                    pages_text.append(ocr_text)
                    ocr_pages += 1
            except Exception as exc:
                logger.warning("OCR failed for page %d of '%s': %s", page_num, filename, exc)
        else:
            logger.debug(
                "Page %d of '%s' has no selectable text and Tesseract is not available — skipping.",
                page_num, filename,
            )

    doc.close()

    if ocr_pages:
        logger.info("'%s': OCR used on %d image-only page(s).", filename, ocr_pages)

    result = "\n\n".join(pages_text)
    logger.info("'%s': extracted %d chars from %d page(s).", filename, len(result), len(pages_text))
    return result


def _extract_image(file_bytes: bytes, filename: str) -> str:
    """
    Extract text from a standalone image file.
    Requires Tesseract. Falls back to empty string if unavailable.
    """
    if _TESSERACT_AVAILABLE:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(img).strip()
            logger.info("'%s': OCR extracted %d chars.", filename, len(text))
            return text
        except Exception as exc:
            raise ExtractionError(f"OCR failed for image '{filename}': {exc}") from exc

    # PyMuPDF fallback — derive filetype from extension so fitz handles it correctly
    if _FITZ_AVAILABLE:
        suffix = Path(filename).suffix.lstrip(".").lower()
        # fitz accepts: png, jpg, jpeg, bmp, webp — normalise jpeg → jpg
        fitz_type = "jpeg" if suffix == "jpg" else suffix
        try:
            doc = fitz.open(stream=file_bytes, filetype=fitz_type)
            text = "\n".join(p.get_text("text").strip() for p in doc).strip()
            doc.close()
            if text:
                return text
        except Exception:
            pass

    logger.warning(
        "'%s': image submitted but Tesseract is not installed — no text extracted. "
        "Install pytesseract + tesseract-ocr to enable image OCR.",
        filename,
    )
    return ""
