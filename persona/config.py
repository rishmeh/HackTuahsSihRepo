"""
persona/config.py — Configuration for the persona package.
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# The robot's name, as the model and the phrase pools refer to it.
PERSONA_NAME: str = os.getenv("PERSONA_NAME", "Tot")

# Piper voice used when nothing else is configured. Matches voice_agent.py.
PIPER_VOICE_MODEL: str = os.getenv("PIPER_VOICE_MODEL", "en_US-lessac-medium.onnx")
