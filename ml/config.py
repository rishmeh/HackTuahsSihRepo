"""
config.py — Central configuration for the ML workflow.

All values can be overridden via environment variables or a .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Local SLM (Ollama)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:2b")
# Separate model for vision (multimodal) requests. Must support image inputs.
OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "llava-phi3")

# Timeout (seconds) for standard (non-thinking) Ollama requests
OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "60"))

# Whether to enable Ollama extended-thinking mode on normal requests.
# Set False to keep responses fast; thinking is enabled selectively on retry.
OLLAMA_THINK: bool = os.getenv("OLLAMA_THINK", "false").lower() == "true"

# Longer timeout for thinking-mode calls (think=True); reasoning takes more time.
OLLAMA_THINK_TIMEOUT: float = float(os.getenv("OLLAMA_THINK_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# Escalation strategy
# ---------------------------------------------------------------------------
# Controls what happens when the SLM has low confidence or requests escalation.
#   "model_thinking" — retry the local SLM with think=True (default, no API key needed)
#   "openrouter"     — forward to OpenRouter (requires OPENROUTER_API_KEY)
ESCALATION_MODE: str = os.getenv("ESCALATION_MODE", "model_thinking")

# SLM confidence score below this triggers escalation (0.0 – 1.0)
ESCALATION_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("ESCALATION_CONFIDENCE_THRESHOLD", "0.6")
)

# ---------------------------------------------------------------------------
# External LLM API (OpenRouter) — used only when ESCALATION_MODE="openrouter"
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
OPENROUTER_TIMEOUT: float = float(os.getenv("OPENROUTER_TIMEOUT", "30"))

# ---------------------------------------------------------------------------
# Safety / moderation
# ---------------------------------------------------------------------------
# Maximum length (characters) of a user query; truncate if exceeded
MAX_QUERY_LENGTH: int = int(os.getenv("MAX_QUERY_LENGTH", "2000"))

# Maximum length of a response before it's considered suspicious
MAX_RESPONSE_LENGTH: int = int(os.getenv("MAX_RESPONSE_LENGTH", "4000"))

# ---------------------------------------------------------------------------
# Conversation history (session memory)
# ---------------------------------------------------------------------------
# Maximum number of past turns (user + assistant pairs) kept per session.
# Higher = more context, more tokens used per request.
MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "10"))

# ---------------------------------------------------------------------------
# Fallback response
# ---------------------------------------------------------------------------
FALLBACK_RESPONSE: str = (
    "I'm having trouble answering that right now. "
    "Please ask your teacher or try rephrasing your question!"
)

# ---------------------------------------------------------------------------
# Vision — face detection and recognition
# ---------------------------------------------------------------------------
# Face settings live in the vision package's own config (vision/config.py),
# which sits outside ml/ so the package can run standalone on the robot.
