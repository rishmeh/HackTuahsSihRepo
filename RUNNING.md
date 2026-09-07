# Running Table Tot — Full Stack

> This guide gets every service in the repo running on a single machine (laptop or desktop).
> All commands are written for **PowerShell on Windows** but translate directly to Bash on macOS/Linux.

---

## Architecture Recap

```
┌─────────────────────────────────────────────────────────────┐
│                       RUNNING SERVICES                       │
│                                                             │
│  :3000  dashboard/  ← React + Express (tRPC, Vite HMR)     │
│  :8000  ml/         ← FastAPI (chat · quiz · flashcards     │
│                               · vision routes               │
│                               · learner routes)             │
│  :11434 Ollama      ← local SLM inference (external)       │
└─────────────────────────────────────────────────────────────┘
```

The `ml/` FastAPI server is the **single Python backend**. It mounts both
`vision/routes.py` and `learner/routes.py` internally — you do **not** run
those packages as separate servers.

`persona/` and `learner/` are Python packages that are imported by `ml/`; they
need no separate process.

---

## Prerequisites

| Tool | Min version | Install |
|---|---|---|
| Python | 3.11 | https://www.python.org/ |
| Node.js | 20 LTS | https://nodejs.org/ |
| pnpm | 10 | `npm install -g pnpm` |
| Ollama | latest | https://ollama.com |
| Git | any | https://git-scm.com/ |

> **Note:** On Raspberry Pi, replace `opencv-contrib-python` with
> `opencv-contrib-python-headless` and skip the dashboard Node setup.

---

## 1 — One-time Setup

### 1a. Python packages (ml + vision + learner + persona)

Run from the **repository root**:

```powershell
# Install the shared top-level packages (vision, learner, persona) in editable
# mode so they are importable from anywhere — including from inside ml/.
pip install -e ".[api,test]"

# Install the full ml service dependencies (torch, transformers, FastAPI, etc.)
pip install -r ml/requirements.txt

# Download the spaCy model used by the PII sanitiser
python -m spacy download en_core_web_sm
```

### 1b. Download face-recognition model weights (~39 MB, one time)

```powershell
python -m vision.download_models
```

### 1c. Dashboard Node dependencies

```powershell
cd dashboard
pnpm install
cd ..
```

### 1d. Configure environment variables

#### ml/.env

```powershell
Copy-Item ml\.env.example ml\.env
# Then open ml\.env in your editor and fill in your OPENROUTER_API_KEY.
# All other values have working defaults — the server starts without them.
```

Key values to set (everything else is optional):

| Variable | What to put |
|---|---|
| `OLLAMA_MODEL` | `qwen3:0.6b` (or whichever you pulled) |
| `OLLAMA_VISION_MODEL` | `llava-phi3` |
| `OPENROUTER_API_KEY` | Your key from https://openrouter.ai |
| `ESCALATION_MODE` | `model_thinking` (offline) or `openrouter` (cloud) |

#### dashboard/.env (optional)

The dashboard picks up `ML_API_URL` to reach the Python backend. The default
(`http://127.0.0.1:8000`) works when everything runs on the same machine.
Create the file only if you change the port:

```powershell
# Only needed if you move the ml server off :8000
"ML_API_URL=http://127.0.0.1:8000" | Out-File dashboard\.env -Encoding utf8
```

### 1e. Pull Ollama models (run once; Ollama must be running)

```powershell
ollama pull qwen3:0.6b      # chat, flashcards, quizzes
ollama pull llava-phi3      # vision endpoint (/chat/vision)
```

---

## 2 — Running Everything

Open **three separate terminal windows** (or PowerShell tabs) from the
repository root and run one command per window.

### Terminal 1 — Ollama (local SLM)

```powershell
ollama serve
```

Ollama will listen on `http://localhost:11434`.

> If Ollama is already running as a system service (common on Windows after
> installation), skip this step — it is already up.

### Terminal 2 — Python Backend (ml)

```powershell
cd ml
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- **Interactive API docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

The `--reload` flag auto-restarts on file changes. Drop it in production.

> **First-run note:** The face-recognition models load lazily on the first
> `/vision/face/*` request, so the startup message appears before they are
> ready. The first request may be slightly slower.

### Terminal 3 — Dashboard (React + Express)

```powershell
cd dashboard
pnpm dev
```

The server logs the URL it binds to (defaults to `http://localhost:3000`).
If port 3000 is taken it automatically picks the next free port.

---

## 3 — Optional: Voice Agent

The voice agent requires a microphone. Run it in a **fourth terminal** while
the ml server (Terminal 2) is already up:

```powershell
cd ml
python voice_agent.py
```

On first run it downloads the Piper TTS model automatically (~63 MB).
Say **"Hey Jarvis"** to activate it.

---

## 4 — Verify Everything Is Up

```powershell
# Python backend health check
Invoke-RestMethod http://localhost:8000/health

# Dashboard (should return HTML)
Invoke-WebRequest http://localhost:3000 -UseBasicParsing | Select-Object StatusCode
```

Expected output from the health check:

```json
{
  "status": "ok",
  "model": "qwen3:0.6b",
  "vision_model": "llava-phi3",
  "escalation_mode": "model_thinking"
}
```

---

## 5 — Running Tests

All tests are run from the **repository root**:

```powershell
# Python tests (vision, learner, persona, ml) — 145+ tests, no models needed
pytest -v

# Dashboard unit tests
cd dashboard
pnpm test
```

---

## 6 — Port Reference

| Port | Service | Notes |
|---|---|---|
| `3000` | Dashboard (React + tRPC) | May auto-shift to 3001+ if busy |
| `8000` | FastAPI ML backend | vision and learner routes included |
| `11434` | Ollama | local SLM inference |

---

## 7 — Troubleshooting

### `ModuleNotFoundError: No module named 'vision'` / `'learner'` / `'persona'`

You skipped the editable install. Run from the repo root:

```powershell
pip install -e ".[api,test]"
```

### `ollama: connection refused` on http://localhost:11434

Ollama is not running. Either run `ollama serve` in a terminal or start the
Ollama desktop app.

### Face model weights missing

```powershell
python -m vision.download_models
```

### Dashboard `pnpm: command not found`

```powershell
npm install -g pnpm
```

### Dashboard cannot reach the ML backend

Check that `ML_API_URL` in `dashboard/.env` matches the address where
`uvicorn` is listening. Default: `http://127.0.0.1:8000`.

### Port 3000 / 8000 already in use

```powershell
# Find what is using the port
netstat -ano | findstr ":8000"

# Kill it (replace <PID> with the number from the output above)
Stop-Process -Id <PID> -Force
```

---

## 8 — Repository Structure Quick Reference

```
HackTuahsSihRepo/
├── ml/                  <- FastAPI backend (start here for Python)
│   ├── main.py          <- uvicorn entry point
│   ├── requirements.txt <- full Python dependency pin
│   └── .env.example     <- copy to .env, add your keys
│
├── dashboard/           <- React + Express + tRPC frontend (start here for Node)
│   ├── package.json     <- pnpm scripts: dev | build | test
│   └── server/          <- Express + tRPC routers
│
├── vision/              <- face detection and recognition package (mounted in ml)
├── learner/             <- onboarding questionnaire and learner profile (mounted in ml)
├── persona/             <- phrase pools and TTS settings (imported by ml)
│
├── pyproject.toml       <- editable install config for vision/learner/persona
└── RUNNING.md           <- this file
```
