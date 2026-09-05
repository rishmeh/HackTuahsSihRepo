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
# Vision — face detection (YuNet) and recognition (SFace)
# ---------------------------------------------------------------------------
# Both models are pretrained and live on-device. Fetch them once with:
#   python -m vision.download_models
VISION_MODELS_DIR: str = os.getenv(
    "VISION_MODELS_DIR", os.path.join(os.path.dirname(__file__), "models")
)
YUNET_MODEL_PATH: str = os.getenv(
    "YUNET_MODEL_PATH",
    os.path.join(VISION_MODELS_DIR, "face_detection_yunet_2023mar.onnx"),
)
SFACE_MODEL_PATH: str = os.getenv(
    "SFACE_MODEL_PATH",
    os.path.join(VISION_MODELS_DIR, "face_recognition_sface_2021dec.onnx"),
)

# Local database of enrolled face embeddings. Never contains images.
FACE_DB_PATH: str = os.getenv(
    "FACE_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "faces.db")
)

# Detector confidence required to call something a face.
#
# Calibrated against measurement: a moving face is reported at a median of 0.833
# and dips well below, while the worst false positive on a faceless image scored
# 0.585. 0.70 sits between them. Raising this towards 0.9 makes the robot lose
# the student whenever they move; lowering it past ~0.59 invents faces.
FACE_DETECT_THRESHOLD: float = float(os.getenv("FACE_DETECT_THRESHOLD", "0.70"))

# Cosine similarity required to accept an identity. OpenCV's published figure
# is 0.363; we run stricter because a false accept loads the wrong student's
# persona and progress, while a false reject only costs a spoken confirmation.
FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.45"))

# Consecutive agreeing frames before announcing that a student has arrived.
FACE_CONFIRM_FRAMES: int = int(os.getenv("FACE_CONFIRM_FRAMES", "3"))

# Consecutive faceless frames before announcing that they have left. At ~5 fps
# this is about a second, so glancing down at a book is not a departure.
FACE_FORGET_FRAMES: int = int(os.getenv("FACE_FORGET_FRAMES", "5"))

# Camera index for cv2.VideoCapture on a laptop. On the Pi, Picamera2 is used
# instead and this is ignored.
CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))

# Frames per second the vision loop targets. Recognition is the expensive
# half; keeping this low leaves CPU for speech and the language model.
VISION_FPS: float = float(os.getenv("VISION_FPS", "5"))
