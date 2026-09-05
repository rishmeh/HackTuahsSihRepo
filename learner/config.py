"""
learner/config.py — Configuration for the learner package.

Self-contained, like vision/config.py: this package sits outside ml/ and must
not import ml/config.py.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # optional for library-only use
    pass

PACKAGE_DIR = Path(__file__).resolve().parent

# Learner profiles, keyed by student id. Holds questionnaire answers and the
# scored profile — no free text from the child, no images, no audio.
LEARNER_DB_PATH: Path = Path(
    os.getenv("LEARNER_DB_PATH", PACKAGE_DIR / "data" / "learner.db")
)

# Below this age sarcasm is off no matter what else the profile says.
SARCASM_MIN_AGE: int = int(os.getenv("SARCASM_MIN_AGE", "11"))
