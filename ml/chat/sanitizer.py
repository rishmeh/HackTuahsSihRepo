"""
chat/sanitizer.py — Strips Personally Identifiable Information (PII)
from a child's query BEFORE it is sent to any language model.

Strategy:
  1. Regex patterns catch structured PII (emails, phone numbers, IDs).  [always runs]
  2. spaCy NER catches names, locations, organisations.                 [runs if available]

spaCy is optional — if its DLL is blocked by OS policy or the package is
missing/incompatible (e.g. Python 3.14), the module degrades gracefully
to regex-only mode with a one-time warning.

The sanitized text is safe to forward to both the SLM and (if escalated)
to the Grok API without exposing the child's identity.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

# spaCy is optional — import errors (blocked DLL, missing package, incompatible
# Python version) are caught here so the rest of the module loads fine.
try:
    import spacy
    from spacy.language import Language as SpacyLanguage
    _SPACY_AVAILABLE = True
except (ImportError, OSError) as _spacy_import_err:
    spacy = None  # type: ignore[assignment]
    SpacyLanguage = None  # type: ignore[assignment,misc]
    _SPACY_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "spaCy could not be imported (%s). "
        "Falling back to regex-only PII sanitization. "
        "To enable NER, install a compatible spaCy build for your Python version.",
        _spacy_import_err,
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns — ordered from most to least specific
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, str]] = [
    # Email addresses
    (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL]"),
    # Phone numbers (various formats)
    (r"\+?[\d][\d\s\-().]{7,}\d", "[PHONE]"),
    # Ages written inline (e.g. "I am 10 years old")
    (r"\b(?:i[\'']?m|i am|aged?|age[: ]+)\s*\d{1,2}\s*(?:years?(?:\s+old)?)?", "[AGE_MENTION]"),
    # Street addresses (simple heuristic)
    (r"\d{1,5}\s+\w+\s+(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|blvd)\b",
     "[ADDRESS]", ),
    # Zip / postal codes
    (r"\b\d{5}(?:-\d{4})?\b", "[POSTAL_CODE]"),
    # "My name is ..." / "I'm ..."
    (r"(?:my name is|i[\'']?m called|call me)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*",
     "[NAME_MENTION]",),
]

_COMPILED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pat, re.IGNORECASE), repl) for pat, repl in _PII_PATTERNS
]

# ---------------------------------------------------------------------------
# spaCy model (loaded once)
# ---------------------------------------------------------------------------

_NLP: Optional[object] = None


def _get_nlp() -> Optional[object]:
    """Lazy-load the spaCy model; fall back gracefully if unavailable."""
    global _NLP
    if _NLP is None:
        if not _SPACY_AVAILABLE:
            return None
        try:
            _NLP = spacy.load("en_core_web_sm")  # type: ignore[union-attr]
            logger.info("spaCy model 'en_core_web_sm' loaded.")
        except OSError:
            logger.warning(
                "spaCy model 'en_core_web_sm' not found. "
                "Run: python -m spacy download en_core_web_sm\n"
                "Falling back to regex-only sanitization."
            )
            _NLP = None
    return _NLP


# Entity labels to redact
_REDACT_LABELS: frozenset[str] = frozenset(
    {"PERSON", "GPE", "LOC", "FAC", "ORG", "NORP"}
)

# Replacement map for NER labels
_LABEL_REPLACEMENT: dict[str, str] = {
    "PERSON": "[NAME]",
    "GPE": "[LOCATION]",
    "LOC": "[LOCATION]",
    "FAC": "[PLACE]",
    "ORG": "[ORGANIZATION]",
    "NORP": "[GROUP]",
}


@dataclass
class SanitizationResult:
    sanitized_text: str
    removed_entities: list[str] = field(default_factory=list)
    pii_detected: bool = False


def sanitize(text: str) -> SanitizationResult:
    """
    Remove PII from *text* and return a SanitizationResult.

    Steps:
      1. Apply regex patterns.
      2. Apply spaCy NER (if model is available).
    """
    removed: list[str] = []

    # --- Step 1: Regex ---
    for pattern, replacement in _COMPILED_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            removed.extend(matches)
            text = pattern.sub(replacement, text)

    # --- Step 2: spaCy NER ---
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text)
        # Process entities in reverse order so span offsets stay valid
        for ent in reversed(doc.ents):
            if ent.label_ in _REDACT_LABELS:
                replacement = _LABEL_REPLACEMENT.get(ent.label_, "[REDACTED]")
                removed.append(ent.text)
                text = text[: ent.start_char] + replacement + text[ent.end_char :]

    return SanitizationResult(
        sanitized_text=text.strip(),
        removed_entities=removed,
        pii_detected=len(removed) > 0,
    )
