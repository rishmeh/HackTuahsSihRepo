# KidBot ML Workflow

Child-safe chat API + quiz generator. Built with FastAPI, Ollama (local SLM), and OpenRouter API.

---

## Architecture

```
ml/
├── config.py                  # Central config (env vars)
├── main.py                    # FastAPI server (/chat, /quiz, /health)
│
├── chat/
│   ├── models.py              # Pydantic schemas (ChatRequest, ChatResponse, SLMResponse)
│   ├── sanitizer.py           # PII removal (regex + spaCy NER)
│   ├── slm_client.py          # Ollama SLM interface
│   ├── complexity_judge.py    # Escalation gate (injection detection)
│   ├── openrouter_client.py   # OpenRouter API interface (receives NO student PII)
│   ├── safety_filter.py       # Output guardrails (child-safety blocklist)
│   └── pipeline.py            # Orchestrates the full chat flow
│
├── quiz/
│   ├── models.py              # Pydantic schemas (QuizRequest, Quiz, QuizQuestion)
│   ├── template.py            # JSON parsing, validation, formatting
│   ├── openrouter_quiz_client.py # High-quality quiz generation via OpenRouter API
│   └── generator.py           # Orchestrates quiz flow
│
└── tests/
    ├── test_sanitizer.py
    ├── test_safety_filter.py
    └── test_quiz_template.py
```

---

## Setup

### 1. Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- An API key from [OpenRouter](https://openrouter.ai/)

### 2. Install dependencies
```bash
cd ml
pip install -r requirements.txt
pip install -e ..    # installs vision/, learner/, persona/ packages (from pyproject.toml)
python -m spacy download en_core_web_sm
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY
```

### 4. Pull Ollama models
You will need a standard chat model and a vision-capable model (for the `/chat/vision` endpoint).

```bash
# Chat model (default in config.py)
ollama pull qwen3.5:2b

# Vision model (default in config.py)
ollama pull llava-phi3
```

### 5. Run the server
```bash
uvicorn main:app --reload --port 8000
```
API docs available at: http://localhost:8000/docs

### 6. Run the Voice Agent (STT & TTS)
The repository includes a laptop voice worker that uses **Moonshine STT**, **Piper TTS**, and **openWakeWord**. It listens for `"Hey Jarvis"` through the laptop microphone and plays synthesized speech through the laptop's default speaker.

In a separate terminal while FastAPI is running, execute:
```bash
python voice_agent.py
```

The first run downloads the speech models. The Pi does not send or receive audio.

---

## Chat Pipeline — Data Boundaries

| Component | Receives | Does NOT receive |
|-----------|----------|-----------------|
| `sanitizer` | Raw query | — |
| `slm_client` | Sanitized query + **full StudentProfile** | — |
| `complexity_judge` | Sanitized query + SLM response | StudentProfile |
| `openrouter_client`| **Sanitized query only** | StudentProfile, name, age, school |
| `safety_filter` | Any LLM output | — |

> **The `openrouter_client` function signature only accepts a `str`** — not a `StudentProfile` — making the PII boundary enforced at the type level, not just convention.

---

## Chat Endpoint

**POST** `/chat`

```json
{
  "query": "How do plants make food?",
  "session_id": "abc-123",
  "student": {
    "name": "Alice",
    "age": 9,
    "grade": "4th grade",
    "personality_traits": ["curious", "visual learner"],
    "interests": ["nature", "art"],
    "language_level": "beginner"
  }
}
```

**Response:**
```json
{
  "answer": "Plants make their food through a process called photosynthesis...",
  "source": "slm",
  "escalated": false,
  "escalation_reason": "none",
  "session_id": "abc-123"
}
```

---

## Quiz Endpoint

**POST** `/quiz`

```json
{
  "student": {
    "age": 10,
    "grade": "5th",
    "personality_traits": ["curious", "visual learner"],
    "covered_topics": ["fractions", "basic geometry", "decimals"]
  },
  "subject": "Mathematics",
  "num_questions": 7
}
```

**Response:** Full `Quiz` JSON with all questions + a `formatted` field containing a human-readable version.

---

## Running Tests

```bash
cd ml
pytest tests/ -v
```

---

## Escalation Flow

```
SLM answers → [safety_filter] → ✅ return to user
                             → 🚫 blocked → fallback message

SLM escalates / low confidence
      → [complexity_judge] checks for injection attempts
              → blocked → fallback message
              → allowed → [openrouter_client] (sanitized query only)
                              → [safety_filter]
                                      → ✅ return to user
                                      → 🚫 blocked → fallback message
```

Any SLM or External API failure returns the friendly fallback:
> *"I'm having trouble answering that right now. Please ask your teacher or try rephrasing your question!"*

---

## Face Detection & Recognition

Face detection and recognition live in the **`vision/` package at the
repository root** and execute on the laptop. The Pi sends JPEG frames to the
hardware endpoint; `main.py` also mounts the face enrolment routes.

See [../vision/README.md](../vision/README.md).

---

## Learner Profiles (onboarding questionnaire)

The 10-scene onboarding questionnaire, its scoring, and the mapping from a
student's profile to how Tot should behave live in the **`learner/` package
at the repository root**. Its endpoints (`/learner/*`) are served by this API.

See [../learner/README.md](../learner/README.md).

---

## Persona (how Tot talks)

Tot's personality lives in the **`persona/` package at the repository root**.
The chat pipeline composes each student's persona onto the SLM system prompt
and wraps answers in code-owned phrase pools; `voice_agent.py` uses the same
pools for its spoken filler lines and takes its Piper pace from the same
settings. `ChatRequest` accepts two optional fields for this: `student_id`
(enrolled student → their persona; otherwise a safe default) and `situation`
(`question | correct_answer | wrong_answer | struggling | repeated_question | idle | greeting`).

See [../persona/README.md](../persona/README.md).

> Note: "vision" is used for two unrelated things in this repo.
> `ml/chat/vision_client.py` and `/chat/vision` mean *multimodal LLM*
> (asking questions about an image). The `vision/` package means
> *camera and faces*.
