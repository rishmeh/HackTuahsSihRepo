# Table Tot — Implementation Playbook

> **Team:** HackTuah | **Event:** Smart India Hackathon 2026 | **PS:** SIH26224

This document breaks the project into **Frontend**, **Backend**, and **Hardware** streams so every team member can pick a lane and know exactly what to build, in what order, and what they depend on.

---

## How to Use This Document

1. Pick your stream: **Frontend**, **Backend**, or **Hardware**.
2. Read the **Your Responsibilities** section for your stream.
3. Follow the **Phases** in order — each phase lists exact steps and files to create.
4. When a step says "depends on X", find X in another stream's earlier phase and coordinate.
5. Each stream has a **Milestone Sign-Off** list — tick these when done so the team knows the project is moving forward.

---

## Architecture Reminder (What Builds What)

Before diving in, everyone should understand the big picture:

```
┌─────────────────────────────────────────────────────────────────┐
│                        PARENT DASHBOARD                          │
│  React + Vite web app · runs in any browser on home WiFi        │
│  KPI charts · study insights · uploads · parental controls       │
└───────────────────────────────▲──────────────────────────────────┘
                                │ REST API + WebSocket
                                │ (local WiFi, no cloud)
┌───────────────────────────────┼──────────────────────────────────┐
│                        RASPBERRY PI 5                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 FASTAPI BACKEND (Python)                  │   │
│  │  REST endpoints · WebSocket live state · scheduler        │   │
│  │  SQLite DB · student persona model                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ STT / TTS    │  │ Vision       │  │ On-device SLM        │   │
│  │ Moonshine    │  │ OpenCV       │  │ Qwen via llama.cpp   │   │
│  │ Kokoro       │  │ YuNet/SFace  │  │ 0.8B 4-bit quant     │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  HARDWARE Abstraction Layer (Python GPIO / PWM / I2C)    │   │
│  │  Camera · Servos · PIR · Display · Mic · Speaker         │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Rule:** The backend owns ALL processing. The frontend is a dashboard + control panel. Hardware is sensors + actuators that the backend drives through GPIO/PWM.

---

# STREAM 1: BACKEND (Python + FastAPI)

**Owns:** All on-device intelligence, voice pipeline, scheduling, SQLite database, REST API, WebSocket live state, and the bridge to hardware.

**Recommended team size:** 2–3 people  
**Primary language:** Python 3  
**Key frameworks/libs:** FastAPI, SQLite, llama.cpp (Python binding), Moonshine, Kokoro, OpenCV, openWakeWord, Silero VAD, all-MiniLM-L6-v2

---

## Phase 0: Environment & Project Skeleton

**Goal:** Get a working Python project on the Pi (or dev machine) with FastAPI running.

### Step 0.1 — Set up the repo structure
Create this inside the backend folder:

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app entry point
│   ├── config.py          # Settings (paths, model paths, GPIO pins)
│   ├── database.py        # SQLite setup + session helpers
│   ├── models/            # SQLAlchemy-style table definitions (or raw SQLite)
│   │   ├── student.py
│   │   ├── session.py
│   │   ├── quiz.py
│   │   └── kpi.py
│   ├── api/
│   │   ├── router.py      # FastAPI routers
│   │   ├── dashboard.py   # Parent dashboard endpoints
│   │   ├── study.py       # Study session endpoints
│   │   └── hardware.py    # Hardware control endpoints
│   ├── services/
│   │   ├── stt.py         # Speech-to-text (Moonshine / Whisper)
│   │   ├── tts.py         # Text-to-speech (Kokoro / ElevenLabs)
│   │   ├── wake_word.py   # openWakeWord wake-word detection
│   │   ├── vad.py         # Silero voice activity detection
│   │   ├── vision.py      # Face detection (YuNet), recognition (SFace), gaze
│   │   ├── ocr.py         # Tesseract / PaddleOCR for notes
│   │   ├── slm.py         # On-device Qwen via llama.cpp
│   │   ├── embeddings.py  # all-MiniLM-L6-v2 for search
│   │   ├── scheduler.py   # Pomodoro / calendar / revision scheduling
│   │   ├── persona.py     # Student persona + adaptive difficulty
│   │   ├── quiz_engine.py # Quiz + flashcard generation
│   │   ├── intent_router.py # Routes queries: SLM vs cloud LLM
│   │   └── escalation.py  # Anonymisation + cloud LLM escalation
│   ├── hardware/
│   │   ├── gpio.py        # GPIO / PWM wrappers for servos, PIR
│   │   ├── camera.py      # Camera capture + OpenCV pipelines
│   │   └── display.py     # IPS display draw commands (C bridge or pygame)
│   ├── websocket.py       # WebSocket live-state broadcaster
│   └── utils.py           # Helpers (logging, anonymisation, etc.)
├── models/                # Downloaded model files (SLM, TTS, STT, etc.)
├── data/                  # SQLite DB + student data + notes
├── requirements.txt
└── run.sh                 # Startup script for the Pi
```

### Step 0.2 — Install dependencies
```bash
# On Raspberry Pi 5 (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3 python3-pip python3-venv libopencv-dev \
    portaudio19-dev libatlas-base-dev ffmpeg tesseract-ocr \
    libtesseract-dev git build-essential

python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn sqlalchemy python-pptx \
    llama-cpp-python moondream-python  # placeholder — pin real versions later
```

Write a `requirements.txt` with pinned versions after you settle on exact model packages.

### Step 0.3 — Hello World FastAPI
In `app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Table Tot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to dashboard IP in production
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "alive", "device": "table-tot"}
```

Run it:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify from another machine on the same WiFi:
```bash
curl http://<PI_IP>:8000/health
```

**Milestone:** FastAPI responds on the Pi's IP from another device. ✅

---

## Phase 1: Database Schema (SQLite)

**Goal:** Define and create the tables that hold everything. All other services read/write through these.

### Step 1.1 — Design the schema

Draw it out first (on paper or a whiteboard):

```
students
  id            TEXT  PRIMARY KEY   (device-generated UUID)
  name          TEXT
  age           INTEGER
  grade         TEXT
  created_at    TEXT

personas
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  mode          TEXT                (friend / teacher / detective)
  tone          TEXT
  difficulty    REAL                (0–1)
  updated_at    TEXT

study_sessions
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  started_at    TEXT
  ended_at      TEXT
  focus_minutes INTEGER
  breaks_taken  INTEGER
  timer_type    TEXT                (pomodoro / normal)

tasks
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  title         TEXT
  due_date      TEXT
  done          INTEGER             (0/1)
  created_at    TEXT

quizzes
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  topic         TEXT
  questions     TEXT                (JSON array)
  score         INTEGER
  taken_at      TEXT

quiz_results
  id            TEXT  PRIMARY KEY
  quiz_id       TEXT  FOREIGN KEY
  question_index INTEGER
  correct       INTEGER
  answered_at   TEXT

notes
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  title         TEXT
  content       TEXT
  ocr_source    TEXT                (path to captured image)
  created_at    TEXT

kpis
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  date          TEXT                (YYYY-MM-DD)
  focus_minutes INTEGER
  quizzes_taken INTEGER
  quizzes_passed INTEGER
  streak_days   INTEGER
  weekly_summary TEXT               (free-text or JSON)

hw_uploads
  id            TEXT  PRIMARY KEY
  student_id    TEXT  FOREIGN KEY
  filename      TEXT
  syllabus_hash TEXT
  ingested_at   TEXT
```

### Step 1.2 — Implement the schema
In `app/database.py`, write functions to:
- Open/close a SQLite connection
- Run `CREATE TABLE IF NOT EXISTS` for each table above on first boot
- Provide a `get_db()` context helper for route handlers

Use raw SQLite (stdlib `sqlite3`) to keep it dependency-light, or SQLAlchemy if the team prefers ORM. Either works — pick one and stick to it.

### Step 1.3 — Write a migration boot script
In `app/main.py` startup event:
```python
@app.on_event("startup")
async def startup():
    init_database()   # creates tables if missing
```

### Step 1.4 — Test the schema
Write a small script `scripts/seed_test_data.py` that:
- Connects to the DB
- Inserts a test student, a task, and a KPI row
- Reads them back
- Runs from the Pi to prove SQLite works on-device

**Milestone:** Boot the Pi, run the seed script, query the DB, confirm rows exist. ✅

---

## Phase 2: Student Persona & Adaptive Engine

**Goal:** A system that remembers a student and adapts difficulty, tone, and prompts.

### Step 2.1 — Persona model
In `app/services/persona.py`:

```python
class Persona:
    def __init__(self, student_id: str):
        self.student_id = student_id
        # load from DB: mode, tone, difficulty, age, grade

    def suggest_prompt_style(self) -> str:
        """Returns 'playful', 'exam_drill', 'story', etc. based on age + mode."""
        ...

    def adjust_difficulty(self, quiz_score: float) -> None:
        """Move difficulty up/down based on recent performance."""
        ...
```

### Step 2.2 — Age-based routing
Add logic:
- Age 6–10 → playful, story mode, short sessions, voice-first
- Age 11–14 → gamified, competitive mode options, moderate sessions
- Age 15–18 → exam-style drills, revision scheduling, longer focus blocks

Store age/grade in the `students` table. Persona reads it on load.

### Step 2.3 — Pattern tracking
Every study session writes to `study_sessions` and `kpis`. The persona service reads recent KPIs to:
- Recommend session length
- Suggest break frequency
- Adjust quiz difficulty

### Step 2.4 — Persist persona changes
When the student completes a quiz or a session, `persona.adjust_difficulty()` writes the new difficulty back to the `personas` table.

**Milestone:** Feed the system a student's age + quiz scores and it returns an appropriate prompt style + updated difficulty. ✅

---

## Phase 3: Scheduler & Timer Engine

**Goal:** Pomodoro timers, normal timers, calendar, alarms, spaced-repetition revision scheduling. The brain that paces study sessions.

### Step 3.1 — Timer core
In `app/services/scheduler.py`:

```python
class TimerEngine:
    def start_pomodoro(self, student_id: str, minutes: int = 25) -> str:
        """Returns a session ID. Fires events at start / tick / break / end."""
        ...

    def start_normal_timer(self, student_id: str, minutes: int) -> str:
        ...

    def cancel_timer(self, session_id: str) -> None:
        ...
```

Use `asyncio.sleep` or a background task queue. Emit WebSocket events on state changes (timer started, tick, break, ended) so the dashboard and the robot face can react.

### Step 3.2 — Calendar & tasks
- Tasks CRUD endpoints (create, list, mark done, delete)
- Due-date reminders: a background task scans `tasks` for overdue/pending items and pushes a reminder via TTS or dashboard notification

### Step 3.3 — Spaced repetition scheduler
In `app/services/scheduler.py` add:

```python
class RevisionScheduler:
    def schedule_revision(self, student_id: str, topic: str, next_review: datetime) -> None:
        """Stores a revision slot in DB."""
        ...

    def get_due_revisions(self, student_id: str) -> list:
        """Returns topics due for review today."""
        ...
```

Use a simplified SM-2-style interval: review intervals grow after each successful recall (1 day, 3 days, 7 days, 16 days, …). Store intervals in a `revisions` table (add to schema if needed).

### Step 3.4 — Session flow orchestration
Build the "study session" orchestrator that wires everything together:
1. Student sits → PIR fires → face recognised → persona loaded
2. Planner screen: today's tasks + due revisions + syllabus
3. Start focus block → Pomodoro timer + posture/hydration nudges (TTS)
4. Active recall break → quiz from the student's notes
5. Wrap up → revision scheduled + KPIs logged

This is the backbone the frontend and hardware will call into.

**Milestone:** Start a Pomodoro timer via API, see WebSocket events fire, timer ends, KPI row written to DB. ✅

---

## Phase 4: Voice Pipeline (STT → Intent → SLM/LLM → TTS)

**Goal:** The robot can hear a student, understand them, answer or quiz them, and speak back — offline-first.

### Step 4.1 — Wake-word detection
In `app/services/wake_word.py`:
- Use openWakeWord (or custom wake word) to listen continuously
- Only when wake word detected, open the audio stream for a short utterance
- Emit a "listening" state over WebSocket so the face animates attention

### Step 4.2 — Voice activity detection
In `app/services/vad.py`:
- Use Silero VAD to trim silence from the captured audio
- Send only voiced segments to STT

### Step 4.3 — Speech-to-text
In `app/services/stt.py`:
- Default: Moonshine (offline, fast on Pi)
- Fallback/online: Whisper (when WiFi available, higher accuracy)
- Return clean text + detected language

### Step 4.4 — Intent router
In `app/services/intent_router.py`:

```python
def route_intent(text: str, student: Student) -> Intent:
    """
    Returns one of:
      - QUIZ_REQUEST      -> quiz_engine
      - KNOWLEDGE_QUERY   -> SLM (or cloud LLM if too hard)
      - TIMER_COMMAND     -> scheduler
      - PERSONA_SWITCH    -> persona
      - CHAT              -> SLM small talk
      - UNCLEAR           -> ask for clarification
    """
```

Start rule-based (keyword matching) — it's enough for V1 and far easier to debug than an LLM classifier. Upgrade to an LLM-based classifier later if time permits.

### Step 4.5 — On-device SLM (Qwen via llama.cpp)
In `app/services/slm.py`:
- Load a quantised Qwen model (0.8B, 4-bit) via llama.cpp Python binding
- On query: run the SLM, cache common replies, return text
- If the query is clearly beyond the SLM's capability (rule: keyword/key-phrase or SLM confidence), escalate to cloud LLM via `escalation.py`

### Step 4.6 — Cloud LLM escalation
In `app/services/escalation.py`:
- Anonymise the query: strip the student's name, personal details, location
- Send anonymised query to cloud LLM API
- Return the answer — never store the raw personal query in cloud logs

### Step 4.7 — Text-to-speech
In `app/services/tts.py`:
- Default: Kokoro-82M (offline, 8 languages including Hindi)
- Fallback: Piper (faster, lower quality)
- Online: ElevenLabs (when WiFi, higher quality)
- Return audio file path or stream to speaker

### Step 4.8 — End-to-end voice loop
Wire it:
```
Wake word → VAD → STT → Intent Router → SLM/LLM → TTS → Speaker
```

Add a WebSocket "listening" / "speaking" / "thinking" state so the face animates at each stage.

**Milestone:** Say the wake word, ask a question, get a spoken answer from the Pi — fully offline. ✅

---

## Phase 5: Vision Pipeline (Face, Gesture, OCR, Gaze)

**Goal:** The robot recognises who is sitting, responds to gestures, reads handwritten notes, and estimates attention.

### Step 5.1 — Face detection + recognition
In `app/services/vision.py`:
- YuNet for face detection (lightweight, runs on Pi)
- SFace for face recognition — match against enrolled faces in a local face DB (store embeddings, NOT images)
- On match: identify student, load persona

### Step 5.2 — Proximity / presence
- PIR motion sensor via GPIO → fires "presence detected" event
- Combined with face recognition → "student X is at the desk"

### Step 5.3 — Gesture control
- OpenCV hand/palm detection (lightweight model or simple contour-based)
- Palm raise → pause timer
- Wave → next slide / next quiz question
- Keep it simple V1: one gesture = pause timer. Add more if time.

### Step 5.4 — OCR for notes
In `app/services/ocr.py`:
- Camera captures an image of a book page or handwritten note
- Tesseract / PaddleOCR extracts text
- Stored in `notes` table with `ocr_source` pointing to the image
- Notes then feed the quiz engine and revision scheduler

### Step 5.5 — Gaze estimation (optional, V2)
- MobileGaze or a lightweight gaze model
- Detect if the student is looking away for too long → fatigue/attention cue
- Mark as optional if the team is behind schedule

**Milestone:** Enrol a face, sit down, get recognised. Point the camera at a note, get text back in the DB. ✅

---

## Phase 6: Quiz & Flashcard Engine

**Goal:** Generate quizzes and flashcards from the student's notes and syllabus — offline.

### Step 6.1 — Quiz generation from notes
In `app/services/quiz_engine.py`:
- Read a note from the `notes` table
- Feed the text to the on-device SLM with a prompt: "Generate 5 quiz questions with answers from this text."
- Parse the SLM output into a structured quiz (JSON)
- Store in `quizzes` table

### Step 6.2 — Quiz taking flow
- Endpoint: `POST /quiz/start` → returns a quiz
- Endpoint: `POST /quiz/answer` → records each answer, computes score
- Results in `quiz_results` + `quizzes.score`

### Step 6.3 — Flashcards
- Same pipeline as quizzes, but output is "term → definition" pairs
- Stored in a `flashcards` table (add to schema if needed)
- Reviewed via spaced repetition (reuse the revision scheduler)

### Step 6.4 — Syllabus ingestion
- Read a syllabus PDF / text upload
- Extract topics with pdfplumber or simple text parsing
- Generate a study plan: topic → suggested session order → revision schedule
- Store the plan in a `study_plan` table (add if needed)

**Milestone:** Upload a note via camera or dashboard, get a quiz back, take it, see the score. ✅

---

## Phase 7: Parent Dashboard API

**Goal:** REST + WebSocket endpoints the React frontend consumes.

### Step 7.1 — REST endpoints
In `app/api/dashboard.py`:

```
GET    /api/student              → list students
GET    /api/student/{id}         → student details + persona
POST   /api/student              → add a student
PUT    /api/student/{id}         → update (name, grade, persona mode)
GET    /api/student/{id}/kpis    → KPI time series
GET    /api/student/{id}/sessions → study session history
GET    /api/student/{id}/quizzes → quiz history + scores
POST   /api/student/{id}/notes   → upload a note (text or OCR result)
GET    /api/student/{id}/revisions → due revisions
PUT    /api/student/{id}/limits  → parental controls (session limits, content filters)
```

### Step 7.2 — WebSocket live state
In `app/websocket.py`:
- Connection: `WS /ws/{student_id}`
- Streams: timer state, face expression, listening status, speaking status, current quiz question
- Frontend subscribes on login and gets real-time updates

### Step 7.3 — Security
- Dashboard is local-network only (bind to Pi's LAN IP, not 0.0.0.0 in production — or firewall off external access)
- No authentication V1 (it's a home LAN), but add a simple PIN gate if time permits
- All personal data stays on-device — no cloud sync of PII

**Milestone:** From a laptop on the same WiFi, hit `GET /api/student` and get a JSON list. Open the WebSocket and see timer state stream. ✅

---

## Phase 8: Integration & On-Device Testing

**Goal:** Everything runs together on the Pi, offline, without crashing.

### Step 8.1 — Boot sequence
Write `run.sh`:
```bash
#!/bin/bash
# 1. Start the display server (C process or pygame)
# 2. Start the FastAPI backend
# 3. Optionally start a watchdog that restarts on crash
```

### Step 8.2 — Resource budgeting
- Profile CPU/RAM usage of each model (STT, TTS, SLM, vision)
- Stagger heavy jobs — don't run STT + SLM + vision simultaneously unless needed
- Use the intent router to decide which models to wake

### Step 8.3 — Offline smoke test
- Disconnect WiFi
- Boot the Pi
- Run through the full session flow: wake word → question → answer → quiz → timer → dashboard
- Everything must work without network

### Step 8.4 — Logging & debugging
- Log to a file with levels (INFO, WARN, ERROR)
- Log model load times, inference times, errors
- Add a `/api/logs` endpoint (last N lines) for on-device debugging from the dashboard

**Milestone:** Full offline session works end-to-end on the Pi. ✅

---

## Backend Milestone Sign-Off

| # | Milestone | Phase |
|---|---|---|
| 1 | FastAPI runs on Pi, responds from another device on WiFi | Phase 0 |
| 2 | SQLite schema created, seed script inserts + reads rows | Phase 1 |
| 3 | Persona loaded from DB, difficulty adjusts after quiz scores | Phase 2 |
| 4 | Pomodoro timer starts/stops, WebSocket events fire, KPI logged | Phase 3 |
| 5 | Full offline voice loop: wake word → STT → SLM → TTS → speaker | Phase 4 |
| 6 | Face recognised on sit-down, OCR note captured to DB | Phase 5 |
| 7 | Quiz generated from a note, taken, score recorded | Phase 6 |
| 8 | Dashboard REST endpoints return JSON, WebSocket streams live state | Phase 7 |
| 9 | Full offline session works end-to-end on the Pi | Phase 8 |

---

# STREAM 2: FRONTEND (Parent Dashboard — React + Vite)

**Owns:** The parent dashboard web app that runs in any browser on the home WiFi. KPI charts, study insights, uploads, parental controls, and live WebSocket visualisation.

**Recommended team size:** 1–2 people  
**Primary stack:** React + Vite + a charting library (Recharts or Chart.js) + CSS (plain or a lightweight framework)

---

## Phase 0: Project Skeleton

### Step 0.1 — Create the Vite React app
On a dev machine (not necessarily the Pi):
```bash
npm create vite@latest table-tot-dashboard -- --template react
cd table-tot-dashboard
npm install
```

### Step 0.2 — Install dependencies
```bash
npm install axios   # REST API calls
# Recharts for KPI charts:
npm install recharts
# Or Chart.js + react-chartjs-2:
# npm install chart.js react-chartjs-2
```

### Step 0.3 — Set up the folder structure
```
table-tot-dashboard/
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── api.js          # Axios base + helper functions for each endpoint
│   ├── websocket.js    # WebSocket client (connects to Pi WS endpoint)
│   ├── context/        # React context for auth/student selection (if any)
│   ├── components/
│   │   ├── Login.jsx              # Student selector / PIN gate (V1: simple selector)
│   │   ├── Dashboard.jsx          # Main layout
│   │   ├── KPICards.jsx           # Focus time, streaks, quiz scores at a glance
│   │   ├── FocusChart.jsx         # Time-series chart of focus minutes
│   │   ├── QuizScoresChart.jsx    # Quiz score trends
│   │   ├── SessionHistory.jsx     # List of past study sessions
│   │   ├── RevisionList.jsx       # Topics due for revision today
│   │   ├── NoteUpload.jsx         # Upload notes / syllabus / homework
│   │   ├── ParentalControls.jsx   # Session limits, content filters, bot behaviour
│   │   ├── LiveStatus.jsx         # WebSocket live state (timer, face, listening)
│   │   └── LiveFace.jsx           # Animated face preview that mirrors the robot
│   ├── styles/
│   │   └── index.css
│   └── assets/
├── index.html
├── package.json
├── vite.config.js
└── README.md
```

### Step 0.4 — Point to the Pi
In `src/api.js`:
```js
import axios from 'axios';

const API = axios.create({
  baseURL: 'http://<PI_IP>:8000/api',  // replace with actual Pi IP
});

export const getStudents = () => API.get('/student');
export const getStudent = (id) => API.get(`/student/${id}`);
export const getKPIs = (id) => API.get(`/student/${id}/kpis`);
export const getSessions = (id) => API.get(`/student/${id}/sessions`);
export const getQuizzes = (id) => API.get(`/student/${id}/quizzes`);
export const getRevisions = (id) => API.get(`/student/${id}/revisions`);
export const uploadNote = (id, note) => API.post(`/student/${id}/notes`, note);
export const updateLimits = (id, limits) => API.put(`/student/${id}/limits`, limits);
```

In `src/websocket.js`:
```js
export function connectWebSocket(studentId, onUpdate) {
  const ws = new WebSocket(`ws://<PI_IP>:8000/ws/${studentId}`);
  ws.onmessage = (event) => {
    onUpdate(JSON.parse(event.data));
  };
  return ws;
}
```

### Step 0.5 — Hello World
In `App.jsx`, render a simple screen that:
- Fetches students via `getStudents()`
- Shows a list
- Clicking a student shows their KPI cards

Run it:
```bash
npm run dev
```

Open `http://localhost:5173` from the dev machine. The backend must be reachable (same WiFi, or use the Pi's IP directly).

**Milestone:** Dashboard loads, fetches students from the Pi, shows KPI cards. ✅

---

## Phase 1: Login / Student Selector

### Step 1.1 — Student picker
Build `Login.jsx`:
- Calls `getStudents()`
- Shows a card for each student (name, grade, current persona mode)
- Clicking selects the student and navigates to the dashboard

### Step 1.2 — PIN gate (optional V1.5)
If time permits, add a 4-digit PIN screen before showing the dashboard. Store the PIN hash in the `students` table. Keep it simple — client-side check is fine for a home LAN demo.

**Milestone:** Select a student → dashboard loads for that student. ✅

---

## Phase 2: KPI Cards + Charts

### Step 2.1 — KPI Cards
Build `KPICards.jsx`:
- Fetches `getKPIs(studentId)`
- Shows: today's focus minutes, current streak, quizzes taken this week, quizzes passed

### Step 2.2 — Focus chart
Build `FocusChart.jsx` using Recharts:
- X axis: date
- Y axis: focus minutes
- Line/bar chart from the KPI time series

### Step 2.3 — Quiz scores chart
Build `QuizScoresChart.jsx`:
- X axis: quiz date
- Y axis: score %
- Shows trend over time

### Step 2.4 — Weekly summary
Show the `weekly_summary` field from the latest KPI row as a text block. Backend writes this (e.g., "Great week! 3.5 hours of focus, 4 quizzes passed.").

**Milestone:** Dashboard shows real KPI numbers and charts from the Pi's DB. ✅

---

## Phase 3: Session History & Revision List

### Step 3.1 — Session history
Build `SessionHistory.jsx`:
- Fetches `getSessions(studentId)`
- Shows a list: date, timer type, focus minutes, breaks taken
- Clicking a session could expand to show more detail (quiz scores that session, etc.)

### Step 3.2 — Revision list
Build `RevisionList.jsx`:
- Fetches `getRevisions(studentId)`
- Shows topics due for revision today with a "Start revision" button
- "Start revision" calls an endpoint (add `POST /student/{id}/revision/start` in backend) that triggers a quiz on that topic

**Milestone:** Dashboard shows past sessions and a list of today's revision topics. ✅

---

## Phase 4: Note / Syllabus Upload

### Step 4.1 — Note upload UI
Build `NoteUpload.jsx`:
- Text area for pasting notes
- File picker for uploading a PDF/image (if backend supports file upload — add `POST /api/student/{id}/notes` with multipart form data)
- Submit → calls `uploadNote()`
- Shows a success toast

### Step 4.2 — Syllabus upload
Similar UI for uploading a syllabus file. Backend ingests it into the study planner.

### Step 4.3 — Homework tracking
Add a section to upload homework with a due date. Appears in the student's task list.

**Milestone:** Upload a note from the dashboard → appears in the backend DB → quiz engine can use it. ✅

---

## Phase 5: Parental Controls

### Step 5.1 — Control panel
Build `ParentalControls.jsx`:
- Session time limit (max minutes per day)
- Content filter toggle (child-safe filtering on/off)
- Persona mode selector (friend / teacher / detective) — overrides student's current mode
- "quiet hours" time window (no notifications during this window)

### Step 5.2 — Wire to backend
- `updateLimits()` calls `PUT /api/student/{id}/limits`
- Backend writes to a `parental_limits` table (add to schema if needed)

**Milestone:** Change a limit on the dashboard → visible in backend DB → enforced in the session flow. ✅

---

## Phase 6: Live WebSocket Dashboard

### Step 6.1 — Live status panel
Build `LiveStatus.jsx`:
- Connects via `connectWebSocket(studentId, onUpdate)`
- Shows: current timer state (focus / break / idle), listening status (idle / listening / speaking / thinking), current quiz question (if any)

### Step 6.2 — Live face preview
Build `LiveFace.jsx`:
- Mirrors the robot's animated face on the dashboard
- The backend sends face expression state over WebSocket (e.g., "happy", "thinking", "listening", "speaking")
- Frontend renders a simple animated face (CSS/SVG) that matches

### Step 6.3 — Real-time chart updates
Optionally update the focus chart in real time as the timer runs (push focus minutes each minute).

**Milestone:** Open the dashboard while a session is running on the robot — see the timer, face, and listening state update live. ✅

---

## Phase 7: Polish & Demo Readiness

### Step 7.1 — Responsive layout
- Make the dashboard usable on a phone browser (parent checking on their phone)
- Stack KPI cards vertically on small screens, charts scrollable

### Step 7.2 — Loading states & error handling
- Show spinners while fetching
- Show friendly error messages if the Pi is unreachable ("Robot is offline — check WiFi")

### Step 7.3 — Demo branding
- Add the HackTuah / Table Tot logo and colours
- Add a short "How to use" tooltip or info panel for the demo

### Step 7.4 — Build for deployment
```bash
npm run build
```
Serve the `dist/` folder from the Pi (e.g., via the FastAPI static file serving, or a simple Python HTTP server) so the dashboard is accessible at `http://<PI_IP>:8000/dashboard` without a separate dev server.

**Milestone:** Built dashboard served from the Pi, accessible from any device on WiFi, demo-ready. ✅

---

## Frontend Milestone Sign-Off

| # | Milestone | Phase |
|---|---|---|
| 1 | Vite React app runs, fetches students from Pi, shows KPI cards | Phase 0 |
| 2 | Student selector → dashboard per student | Phase 1 |
| 3 | KPI cards + focus chart + quiz score chart show real data | Phase 2 |
| 4 | Session history + revision list displayed | Phase 3 |
| 5 | Note/syllabus upload works, content appears in backend | Phase 4 |
| 6 | Parental controls change limits visible in backend | Phase 5 |
| 7 | Live WebSocket shows timer state + face expression in real time | Phase 6 |
| 8 | Dashboard built, served from Pi, demo-ready on phone + laptop | Phase 7 |

---

# STREAM 3: HARDWARE (Raspberry Pi 5 + Peripherals)

**Owns:** All physical components — Pi 5, servos, camera, display, mic, speaker, PIR sensor — and the GPIO/PWM/display software layer that the backend drives.

**Recommended team size:** 1–2 people (ideally one with electronics experience)  
**Primary board:** Raspberry Pi 5 (4 GB)  
**Key libraries:** GPIOZERO or RPi.GPIO, OpenCV, PWM via GPIO, display via pygame or a C bridge

---

## Phase 0: Inventory & Bench Setup

### Step 0.1 — Confirm parts
From the BOM in the presentation:

| Component | Qty | Role |
|---|---|---|
| Raspberry Pi 5 (4 GB) | 1 | Main compute |
| BeagleBone | 1 | Development board (secondary) |
| Servos (micro/standard) | 2 | Head + body movement |
| Camera module (CSI or USB) | 1 | Face, gesture, OCR |
| IPS display (HDMI or SPI) | 1 | Animated face + UI |
| USB microphone | 1 | Voice input |
| USB speaker / amplified speaker | 1 | Voice output |
| PIR motion sensor | 1 | Presence detection |

### Step 0.2 — Verify what's already in hand
- Check which items the team already has vs needs to source
- For any missing items, note the order link / local store + estimated cost

### Step 0.3 — Set up the bench
- Get a breadboard, jumper wires (male-to-female + male-to-male), a 5V power supply for the Pi, and a separate power source for servos if they draw more than the Pi's GPIO can safely supply
- **Important:** Servos should be powered from a separate 5V rail, not the Pi's 5V pin, to avoid brown-outs. Use a common ground.

**Milestone:** All parts accounted for, bench set up, power plan clear. ✅

---

## Phase 1: Pi OS & Basic Config

### Step 1.1 — Install OS
- Flash Raspberry Pi OS (64-bit) to the SD card / SSD
- Enable SSH, set a static LAN IP (so the frontend always finds it), configure WiFi

### Step 1.2 — System updates
```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

### Step 1.3 — Install system deps (shared with backend)
```bash
sudo apt install -y python3 python3-pip python3-venv python3-gpiozero \
    python3-rpi-gpio libopencv-dev portaudio19-dev libatlas-base-dev \
    ffmpeg tesseract-ocr libtesseract-dev git build-essential i2c-tools
```

### Step 1.4 — Enable hardware interfaces
- Enable I2C / SPI / GPIO via `raspi-config` if the display or sensors need them
- Test each interface:
  - `i2cdetect -y 1` to see I2C devices
  - `ls /dev/video*` to confirm the camera
  - `arecord -l` / `aplay -l` to confirm mic + speaker

**Milestone:** Pi boots, SSH works, camera/mic/speaker all visible to the OS. ✅

---

## Phase 2: PIR Presence Sensor

### Step 2.1 — Wire the PIR
- PIR VCC → 5V (separate rail or Pi 5V with caution)
- PIR GND → GND
- PIR OUT → GPIO pin (e.g., GPIO 17)

### Step 2.2 — Test with GPIOZERO
```python
from gpiozero import MotionSensor
from time import sleep

pir = MotionSensor(17)

while True:
    if pir.motion_detected:
        print("MOTION!")
    sleep(0.5)
```

### Step 2.3 — Integrate with backend
In `app/hardware/gpio.py`, wrap the PIR:
```python
from gpiozero import MotionSensor

class PIR:
    def __init__(self, pin=17):
        self.sensor = MotionSensor(pin)
        self.callback = None

    def on_motion(self, callback):
        self.sensor.when_motion = callback
```

Backend registers a callback that:
- Fires a "presence detected" event
- Triggers face recognition to identify who sat down
- Starts the "wake up" face animation

**Milestone:** Sit down in front of the robot → backend logs "presence detected" → face wakes up. ✅

---

## Phase 3: Camera — Face, Gesture, OCR

### Step 3.1 — Camera setup
- Connect the camera module (CSI) or USB camera
- Verify with `libcamera-hello` or `fswebcam`
- In `app/hardware/camera.py`, write a capture function that returns a numpy image

### Step 3.2 — Face detection (YuNet)
In `app/services/vision.py`:
- Load YuNet via OpenCV DNN or the OpenCV Zoo API
- Run on each captured frame (or every Nth frame to save CPU)
- Return bounding boxes

### Step 3.3 — Face recognition (SFace)
- Maintain a local face embedding DB (store embeddings, not images)
- Enrol faces: capture several frames of a student, average the embeddings, store with student ID
- On detection: run SFace, match against the DB, return student ID or "unknown"

### Step 3.4 — Gesture detection (V1: palm raise)
- Simple approach: detect a raised hand via contour or a lightweight hand detector
- Palm raise → publish a "gesture: pause" event to the backend
- Backend pauses the active timer

### Step 3.5 — OCR capture
- When the student triggers a note capture (voice command or button), snap a high-res image
- Run Tesseract / PaddleOCR on it
- Return extracted text to the backend → stored in `notes` table

**Milestone:** Robot recognises an enrolled face. Palm raise pauses the timer. Camera captures a note and extracts text. ✅

---

## Phase 4: Servo-Driven Head & Body Movement

### Step 4.1 — Wire the servos
- Servo signal wire → GPIO PWM pin (e.g., GPIO 12 + 13 for two servos)
- Servo power → separate 5V rail
- Common ground with Pi

### Step 4.2 — Test servo movement
With GPIOZERO:
```python
from gpiozero import Servo
from time import sleep

servo = Servo(12)

servo.max()      # one extreme
sleep(1)
servo.mid()      # centre
sleep(1)
servo.min()      # other extreme
```

### Step 4.3 — Map movements to expressions
Define a movement vocabulary:
- **Idle:** gentle slow sway
- **Listening:** tilt forward slightly
- **Speaking:** small nods
- **Happy:** quick bounce
- **Thinking:** head tilt to side

In `app/hardware/gpio.py`, expose:
```python
class ServoController:
    def idle(self): ...
    def listen(self): ...
    def speak(self): ...
    def happy(self): ...
    def thinking(self): ...
```

Backend calls these based on WebSocket state / session phase. The frontend's live face preview mirrors the same state.

### Step 4.4 — Duty cycle for heat management
- Don't hold servos at extreme positions continuously
- Use short moves with rests in between
- Log servo activity to track duty cycle

**Milestone:** Robot head/body moves in response to session states (idle, listening, speaking, happy). ✅

---

## Phase 5: IPS Display — Animated Face + UI

### Step 5.1 — Display connection
- If HDMI display: plug into Pi's HDMI port, configure `config.txt` for resolution
- If SPI display: wire SPI bus, install the driver, test with a hello-world draw

### Step 5.2 — Choose the drawing stack
Options:
- **Pygame** (Python, simple, good for animated faces + basic UI) — recommended for V1
- **C/C++** display process (faster, but more work) — Phase 8 if time
- **SDL2** via Python bindings

For V1, start with pygame. It's pure Python and fast enough for a face animation + simple UI overlays.

### Step 5.3 — Animated face
In `app/hardware/display.py` (or a separate display process):
- Draw a face: eyes, mouth, eyebrows
- Animate based on state from backend:
  - **Idle:** eyes open, neutral mouth, gentle blink
  - **Listening:** eyes wide, mouth slight smile
  - **Speaking:** mouth opens/closes (animated)
  - **Thinking:** eyebrows raised, mouth neutral
  - **Happy:** big smile, bright eyes
  - **Sleeping/standby:** eyes closed

### Step 5.4 — UI overlays
- When in planner mode: show today's tasks + due revisions on the display
- When in quiz mode: show the current question
- Keep the UI minimal — the face is the main visual, text overlays are secondary

### Step 5.5 — Bridge to backend
- Have the display process read state from a local pipe / shared file / localhost socket that the backend writes to
- Or have the display be a pygame window that the backend drives directly via function calls (simpler for V1)

**Milestone:** Animated face on the display reflects the robot's current state (idle/listening/speaking/thinking/happy). ✅

---

## Phase 6: Microphone & Speaker — Audio I/O

### Step 6.1 — Mic setup
- Plug in the USB mic
- Test with `arecord -d 5 test.wav` then play it back
- Confirm the backend's STT service can read from the mic (PyAudio or sounddevice)

### Step 6.2 — Speaker setup
- Plug in the USB speaker or amplified speaker
- Test with `aplay test.wav`
- Confirm the backend's TTS service can play back audio

### Step 6.3 — Audio pipeline integration
- STT service reads from mic → returns text
- TTS service writes audio to speaker
- Add a small mixer/routing layer if needed to avoid feedback (mic picking up speaker output)

### Step 6.4 — Volume & sensitivity tuning
- Set mic gain so it picks up a normal speaking voice at desk distance
- Set speaker volume comfortable for a desk environment
- Log audio levels for debugging

**Milestone:** Robot listens via mic, speaks via speaker, no significant feedback. ✅

---

## Phase 7: System Assembly & Enclosure

### Step 7.1 — Mechanical mounting
- Mount the camera at face height on the robot body
- Mount the display as the "face" screen
- Mount servos so the head can tilt (1 servo) and the body can sway (1 servo)
- Keep the Pi accessible for debugging (removeable panel or open bench for V1)

### Step 7.2 — Wiring management
- Bundle wires, label them
- Separate servo power from Pi power (common ground, separate 5V)
- Add a switch to cut servo power independently

### Step 7.3 — Thermal design
- Add a heatsink + small fan to the Pi
- Vent the enclosure
- Monitor Pi temperature (`vcgencmd measure_temp`) during sustained load

### Step 7.4 — Power
- Pi: official 5V/5A USB-C PSU (or equivalent)
- Servos: separate 5V rail (e.g., a small buck converter from a higher voltage, or a dedicated 5V PSU)
- Total current budget: Pi (~1–3A under load) + servos (~0.5–1A each under load) + display + peripherals

**Milestone:** Robot assembled, powers on, all peripherals function, Pi stays cool under load. ✅

---

## Phase 8: Hardware-Software Integration

### Step 8.1 — End-to-end boot
- Power on → Pi boots → backend starts → display shows face → PIR active → mic listening
- Verify each subsystem comes up in the right order

### Step 8.2 — Full session walkthrough (hardware in the loop)
Run the full flow with the physical robot:
1. Walk up → PIR fires → face recognises → persona loaded → display shows "hello"
2. Say "start a Pomodoro" → timer starts → servo does focus posture → display shows timer
3. During timer → hydration/posture nudges via TTS + face expression
4. Palm raise → timer pauses → servo reacts
5. Say "quiz me" → quiz question on display + spoken → answer via voice → score on display
6. Walk away → PIR no motion → robot goes to standby face

### Step 8.3 — Robustness checks
- What happens if the camera is blocked? (fallback to PIR-only mode)
- What happens if the mic is silent? (timeout, ask user to speak up)
- What happens if a servo stalls? (log error, continue without movement)
- What happens if WiFi drops? (graceful degradation — all offline features still work)

### Step 8.4 — Demo prep
- Prepare a scripted demo flow that hits the highlights in 3–5 minutes
- Have a backup: if a hardware component fails during demo, the backend + dashboard should still show the intelligence (run the backend on a laptop as a fallback for the demo)

**Milestone:** Full hardware-in-the-loop session works. Demo flow is scripted and practised. ✅

---

## Hardware Milestone Sign-Off

| # | Milestone | Phase |
|---|---|---|
| 1 | All parts accounted for, bench set up, power plan clear | Phase 0 |
| 2 | Pi boots, SSH works, camera/mic/speaker visible to OS | Phase 1 |
| 3 | PIR detects presence → backend logs event → face wakes up | Phase 2 |
| 4 | Face recognised on sit-down; palm raise pauses timer; OCR note captured | Phase 3 |
| 5 | Servo head/body moves in response to session states | Phase 4 |
| 6 | Animated face on display reflects idle/listening/speaking/thinking/happy | Phase 5 |
| 7 | Mic + speaker work, audio pipeline functional, no feedback | Phase 6 |
| 8 | Robot assembled, powered, cooled, all peripherals functional | Phase 7 |
| 9 | Full hardware-in-the-loop session + scripted demo flow | Phase 8 |

---

# CROSS-STREAM DEPENDENCIES (Read This First)

Some steps in one stream depend on another stream finishing earlier. Here's the map:

### Backend depends on:
- **Hardware Phase 1** (Pi OS ready, camera/mic/speaker visible) — before backend can use them
- **Hardware Phase 2** (PIR wired + tested) — before backend can use presence events
- **Hardware Phase 5** (display working) — before backend can drive the animated face

### Frontend depends on:
- **Backend Phase 0** (FastAPI running) — before frontend can call any API
- **Backend Phase 1** (DB schema) — before frontend can show real KPIs/sessions
- **Backend Phase 7** (dashboard API endpoints + WebSocket) — before frontend can build the live dashboard

### Hardware depends on:
- **Backend Phase 0** (FastAPI running) — before hardware abstraction layer can be driven by the backend
- **Backend Phase 4** (voice pipeline) — before mic/speaker are used intelligently

### Sequence recommendation:
1. **Backend Phase 0 + Hardware Phase 0–1** in parallel (get the Pi ready + get FastAPI running)
2. **Backend Phase 1–3** (DB, persona, scheduler) — no hardware needed yet, can test on a laptop
3. **Frontend Phase 0–2** in parallel (dashboard skeleton + KPI cards)
4. **Backend Phase 4–6** (voice, vision, quiz) + **Hardware Phase 2–6** in parallel (wire sensors, camera, servos, display, audio)
5. **Backend Phase 7** + **Frontend Phase 3–6** in parallel (dashboard API + frontend pages)
6. **Backend Phase 8** + **Hardware Phase 7–8** + **Frontend Phase 7** (integration, assembly, polish, demo prep)

---

# ROLE ASSIGNMENT SUGGESTIONS

If your team has 4–6 members, a sensible split:

| Role | Stream | Focus |
|---|---|---|
| **Backend Lead** | Backend | FastAPI, DB, SLM integration, voice pipeline, API design |
| **Backend Engineer** | Backend | Vision pipeline, quiz engine, scheduler, persona, WebSocket |
| **Frontend Engineer** | Frontend | Dashboard UI, charts, WebSocket client, build + deploy |
| **Frontend/UX (optional)** | Frontend | Polish, responsive, demo branding, live face preview |
| **Hardware Lead** | Hardware | Pi setup, GPIO, servos, PIR, camera, display, assembly |
| **Hardware/Integration (optional)** | Hardware | Audio I/O, enclosure, thermal, end-to-end testing |

If you have fewer people, one person can own both Backend + Hardware (they're tightly coupled on the Pi), and another owns Frontend.

---

# WHAT "DONE" LOOKS LIKE FOR THE DEMO

A successful SIH demo runs the full story in 3–5 minutes:

1. **Robot is idle** on the desk, face showing standby animation
2. **Student walks up** → PIR fires → face recognises → persona loads → face greets
3. **Plan the session** — dashboard or voice: "What's today?" → tasks + revisions shown
4. **Focus block** — start Pomodoro → timer running on display + dashboard → servo posture → posture/hydration nudge via TTS
5. **Active recall break** — quiz from the student's notes → voice answer → score shown
6. **Parent checks dashboard** on their phone — sees focus time, streak, quiz scores updating live
7. **Wrap up** — revision scheduled, KPIs logged

If any hardware component fails during the demo, the backend can run on a laptop and the dashboard still shows the intelligence. That's the fallback.

---

# TIMELINE SUGGESTION (Relative, Adjust to Your Schedule)

| Week | Focus |
|---|---|
| **Week 1** | Pi setup, FastAPI skeleton, DB schema, frontend skeleton + student list + KPI cards |
| **Week 2** | Persona + scheduler + timer engine, dashboard KPI charts + session history, PIR + camera basic capture |
| **Week 3** | Voice pipeline (wake word → STT → SLM → TTS), face recognition + OCR, quiz engine, dashboard revision list + note upload |
| **Week 4** | Servo control + animated face on display, dashboard parental controls + live WebSocket, system assembly |
| **Week 5** | Full integration, offline smoke test, robustness checks, demo script + rehearsal, polish |

Adjust the weeks to your actual hackathon timeline. The phase numbers are the source of truth — re-sequence the weeks as needed.

---

# FILE INDEX (What Each Stream Produces)

### Backend produces:
```
backend/
├── app/main.py, config.py, database.py
├── app/models/*.py
├── app/api/*.py
├── app/services/*.py
├── app/hardware/*.py
├── app/websocket.py
├── requirements.txt
└── run.sh
```

### Frontend produces:
```
table-tot-dashboard/
├── src/main.jsx, App.jsx, api.js, websocket.js
├── src/components/*.jsx
├── src/styles/index.css
├── package.json
├── vite.config.js
└── dist/                 # built output (Phase 7)
```

### Hardware produces:
```
hardware/
├── wiring/           # diagrams, photos, pin maps
├── enclosure/        # sketches, dimensions, 3D print files (if any)
├── test_scripts/     # standalone test scripts per component
└── assembly_notes.md # assembly steps, power plan, thermal plan
```

---

## Quick-Start for Each Team Member

**If you're Backend:** Start with Phase 0 — get FastAPI running on the Pi, then Phase 1 — build the DB schema. You can do both of these without any hardware beyond the Pi itself.

**If you're Frontend:** Start with Phase 0 — create the Vite app, hardcode the Pi IP, fetch `GET /health` from the backend. Once the backend has Phase 1 (DB), build Phase 2 (KPI cards).

**If you're Hardware:** Start with Phase 0 — inventory the parts, then Phase 1 — flash the Pi OS, enable SSH, confirm camera/mic/speaker. Then Phase 2 — wire and test the PIR.

Pick your Phase 0 today. The rest follows in order.
