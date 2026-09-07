# Table Tot — AI-Powered Desk Companion Robot

> **Smart India Hackathon 2026** | Problem Statement: SIH26224 — Student Innovation  
> **Theme:** Smart Education | **Category:** Hardware | **Team:** HackTuah

Startup instructions: [START_ROBOT.md](START_ROBOT.md)

Wiring and power: [hardware/CONNECTIONS.md](hardware/CONNECTIONS.md)

![Smart India Hackathon 2026](https://sih.gov.in/)

---

## Overview

**Table Tot** is an AI-powered desk companion robot that lives on a student's study desk. It learns the student's routine and study patterns, then builds personalised productivity workflows around them. A laptop runs every model and application service and uses its own microphone and speakers. A Raspberry Pi 5 inside the robot handles the camera, animated-face display and two servos.

---

## Problem Statement

Students today face three unresolved challenges:

| Challenge | How Table Tot Addresses It |
|---|---|
| **No structured self-study guidance** | Builds and enforces a personal study rhythm: timers, revision scheduling and reminders |
| **Study apps are easy to ignore** | A physical companion with voice, gestures and expressions creates engagement and accountability |
| **Parents have no visibility** | A local web dashboard shows study insights without intrusive surveillance |

---

## Innovation & Uniqueness

### Offline-First by Design
A small language model on the laptop answers questions and builds quizzes offline, and decides when a cloud LLM is really needed. The Pi and laptop only need a local wired or Wi-Fi network; internet access is optional.

### Age and Psychology Adaptive
Difficulty, prompts, tone and personality adjust to the student's developmental stage and observed study patterns. A 9-year-old gets playful story prompts; a Class 12 student gets exam-style drills.

### Multi-Modal Interaction
Voice through the laptop, camera-based gesture control and face recognition give a hands-free way to study. Raise a palm to pause the timer; the camera recognizes when the student sits down.

### Dynamic Personality
Friend, teacher or detective personas, plus an expressive animated face, keep engagement fresh across age groups. Detective mode turns a history chapter into clues to solve.

---

## Key Features

### Study Tools
- Pomodoro and normal timers, alarms
- To-do list and calendar
- AI tutor: on-device SLM + cloud
- Quizzes and flashcards, offline
- Notes with OCR from books and handwriting
- Daily news and general knowledge feed

### Smart Interaction
- Voice input and spoken replies
- Face recognition from the Pi camera
- Gesture control for hands-free use
- Laptop dashboard and robot-status display
- Servo-driven head and body movement
- Student persona and pattern tracking

### Wellness and Safety
- Hydration, posture and break reminders
- Fatigue cues from camera and usage
- Child-safe content filtering
- All personal data stays on-device
- No cloud storage of face or voice
- Cloud queries anonymised first

### Parent Dashboard
- KPI tracking: focus time, streaks, quiz scores
- Study insights and weekly summaries
- Controls over bot behaviour and limits
- Upload notes, syllabus and homework
- Any browser on the home WiFi, no app install

---

## A Study Session with Table Tot

1. **Student sits down** — Pi camera frames reach the laptop, the face is recognised and the persona loads
2. **Plan the session** — Today's to-dos, syllabus and due homework
3. **Focus block** — Pomodoro timer, posture and hydration nudges
4. **Active recall break** — Voice quiz from the student's own notes
5. **Wrap up** — Revision scheduled, KPIs logged to dashboard

---

## Content Intelligence

- Syllabus ingestion and automatic study planner
- Last-minute revision notes generation
- Spaced-repetition revision scheduling
- Homework upload and tracking
- Curated open-source videos and articles

## Engagement and Learning Modes

- Robot personalities: friend, teacher, detective
- Story-based and game-based learning
- Competitive mode and group learning
- Public speaking and language practice
- Concept animations generated with Manim

---

## Connectivity Model: Self-Sufficient Offline, Smarter Online

### Offline Mode — Always Available

| Capability |
|---|
| Timers, alarms, calendar, to-do |
| On-device SLM: Q&A and quizzes |
| Moonshine STT and Piper TTS on the laptop |
| Face detection (YuNet) |
| Wellness reminders |
| Scheduling, persona, KPIs |

**Storage:** SQLite plus a quantised SLM; scheduling and persona data stay local.

### Online Mode — When WiFi is Available

| Capability |
|---|
| Cloud LLM for hard questions |
| New flashcards and quizzes |
| Daily news and GK feed |
| Whisper STT, ElevenLabs TTS |
| Module download and updates |
| Syllabus and content ingestion |

**Escalation:** Queries are anonymised before sending; no personal data is pushed. The router decides when to switch.

---

## Technical Approach

### Hardware

| Component | Role |
|---|---|
| Laptop | All AI, application, database and dashboard computation |
| Raspberry Pi 5 (4 GB) | Camera, face-display and servo bridge |
| 2 × Servos | Head and body movement |
| Camera module | Face, gesture, OCR |
| Laptop microphone + speakers | Voice input and spoken replies |
| HDMI IPS display | Animated robot face, driven by the Pi |
| Laptop screen | Parent dashboard and diagnostics |

> Pi, servos and camera are already in hand. BOM stays affordable.

### Software Stack

| Layer | Technology |
|---|---|
| Language | Python |
| Backend | FastAPI on the laptop; HTTP bridge to the Pi |
| Database | SQLite — offline-first, zero-setup local DB |
| Vision | OpenCV |
| Offline Speech | Moonshine (STT) + Piper (TTS), both on the laptop |
| Dashboard | React + Vite — parent dashboard over WiFi |
| Local SLM | Qwen through Ollama on the laptop |
| Ingestion | pdfplumber, Tesseract, FFmpeg, Whisper |

### Voice Pipeline: Laptop SLM First, Cloud LLM Only When Needed

```
Wake word detection (openWakeWord)
    ↓
Speech-to-text: Moonshine (offline) / Whisper (online)
    ↓
Intent router
    ↓
SLM on laptop → cloud LLM if needed
    ↓
Text-to-speech: Piper on the laptop
    ↓
Laptop speaker + Pi servo command
```

### Laptop Models

| Model | Purpose |
|---|---|
| Piper | TTS |
| Moonshine | STT |
| openWakeWord | Wake word detection |
| Silero VAD | Voice activity detection |
| YuNet | Face detection |
| SFace | Face recognition |
| MobileGaze | Gaze estimation |
| Tesseract / PaddleOCR | OCR |
| Qwen local SLM | Image + text Q&A |
| all-MiniLM-L6-v2 | Embeddings and search |

---

## System Architecture

```
ROBOT / RASPBERRY PI 5                  LAPTOP
────────────────────────────────────────────────────────────────────
Camera ──JPEG over HTTP───────────────▶ YuNet + SFace recognition

Servos ◀──versioned JSON state───────── Robot state machine
Display ◀──versioned face state──────── FastAPI application services
                                        Laptop microphone + Moonshine
                                        Piper + laptop speakers
                                        Ollama SLM, SQLite, dashboard
────────────────────────────────────────────────────────────────────
             trusted LAN, laptop TCP port 8000
```

- Personal records, models and audio stay on the laptop. The Pi retains no face image and renders the animated face locally from state names.
- The dashboard and Pi use the laptop FastAPI service on the local network.
- Camera transfer and servo return commands are documented in `hardware/DATA_FLOW.md`.
- The query scrubber is the only path to an optional cloud model.

---

## Feasibility and Viability

### Why It Is Feasible

- **Affordable:** Total bill of materials per unit is low; all parts are off-the-shelf and commercially available.
- **Parts in hand:** Pi, camera and servos already available.
- **Fully open-source stack:** Python, FastAPI, OpenCV, Moonshine, Piper, Ollama and React.
- **Huge Pi community:** Documented drivers for every peripheral used.
- **Works without internet:** The laptop SLM answers everyday questions offline while the Pi and laptop communicate over the LAN.
- **Own it forever:** The local SLM is a one-time cost, while cloud API bills compound over time.

| Metric | Value |
|---|---|
| Recurring AI cost offline | **Rs 0/mo** |
| Personal records in cloud | **0** |

### Potential Challenges and Risks

| Challenge | Strategy |
|---|---|
| **Laptop availability** — the robot depends on its paired laptop | Reserve stable LAN addresses and start the laptop service before a study session |
| **Voice latency offline** — Local STT / TTS is slower than cloud | Wake-word gating: listen for the wake word only, then stream short utterances; pre-cache common replies |
| **Child data privacy** — Face, voice and study patterns are sensitive | Keep records and models on the laptop, discard Pi capture buffers, and anonymise optional cloud queries |
| **Servo power noise** — servo current spikes can reset the Pi | Separate regulated servo supply, common ground and bulk capacitance near the servos |

---

## Impact and Benefits

### Target Audience

- **Primary:** K-12 and college students who self-study at home
- **Secondary:** Parents, teachers, coaching centres and libraries

### Educational

| Outcome |
|---|
| Dedicated, distraction-free study companion replaces passive screen time |
| Spaced repetition and revision scheduling improve long-term retention |
| Active-recall quizzes built from the student's own notes |
| Adaptive difficulty keeps every age group engaged |

> **Impact:** Higher retention, less last-minute cramming

### Social

| Outcome |
|---|
| Bridges the parent-student gap with insight, not surveillance |
| Physical, expressive companion supports students who study alone |
| Group and competitive modes encourage peer learning |
| Laptop microphone supports hands-free study interaction |

> **Impact:** Trust between parents and students

### Economic

| Outcome |
|---|
| Low bill of materials makes it affordable for middle-income Indian homes |
| Offline-first design serves areas with poor connectivity |
| Scales to schools, libraries and government learning centres with minimal infrastructure |
| Replaces paid apps and subscriptions; no recurring AI bill |

> **Impact:** Affordable and deployable at scale

### Wellness

| Outcome |
|---|
| Hydration, posture and break reminders reduce strain during long sessions |
| Fatigue cues trigger a break or a lighter activity |
| Personas and story mode make studying feel less like a chore |
| No doom-scrolling: the companion has no social feed |

> **Impact:** Healthier, sustainable study habits

---

## Research and References

### Learning Science

- **Pomodoro Technique.** Cirillo, F. (2006). *The Pomodoro Technique.* [pomodorotechnique.com](https://pomodorotechnique.com)
- **Spacing and retention.** Cepeda et al. (2006). Distributed practice in verbal recall tasks. *Psychological Bulletin.* [doi.org/10.1037/0033-2909.132.3.354](https://doi.org/10.1037/0033-2909.132.3.354)
- **Active recall.** Roediger and Karpicke (2006). Test-enhanced learning. *Psychological Science.* [doi.org/10.1111/j.1467-9280.2006.01693.x](https://doi.org/10.1111/j.1467-9280.2006.01693.x)
- **Forgetting curve.** Ebbinghaus, H. (1885). *Memory: A contribution to experimental psychology.* [psychclassics.yorku.ca](https://psychclassics.yorku.ca/Ebbinghaus/index.htm)
- **Policy.** National Education Policy 2020, Ministry of Education, Govt. of India. [static.pib.gov.in](https://static.pib.gov.in/WriteReadData/userfiles/NEP_Final_English_0.pdf)

### Technology

- **Qwen3.** Alibaba. Open-weight small language models for on-device use. [github.com/QwenLM/Qwen3](https://github.com/QwenLM/Qwen3)
- **llama.cpp.** Quantised LLM inference in C/C++ on CPU. [github.com/ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)
- **Moonshine.** Useful Sensors. Real-time on-device speech recognition. [github.com/usefulsensors/moonshine](https://github.com/usefulsensors/moonshine)
- **OpenCV Zoo.** YuNet face detection and SFace face recognition. [github.com/opencv/opencv_zoo](https://github.com/opencv/opencv_zoo)
- **piper-tts.** Rhasspy. Local neural TTS used on the laptop. [github.com/rhasspy/piper](https://github.com/rhasspy/piper)
- **Raspberry Pi docs.** Camera, GPIO and PWM servo control. [raspberrypi.com/documentation](https://raspberrypi.com/documentation)

### Comparable Products

| Product | Limitation | Table Tot Differentiator |
|---|---|---|
| **Miko** (India) | Companion robot for kids; cloud-dependent, no study workflow or OCR | Offline-first AI, study-specific workflows, OCR, parent dashboard |
| **Amazon Echo Show Kids** | Voice-first, no physical expressiveness or study tracking | Physical robot with animated face, gestures, study tracking |
| **Wonder Workshop Cue** | Coding-focused robot, not a study companion | Purpose-built study companion with AI tutor and revision scheduling |
| **Emo / Loona desk robots** | Emotive desk pets with no study workflow, OCR or parent view | Study workflows, OCR, parent dashboard, on-device privacy |

---

## Repository Structure

```
HackTuahsSihRepo/
├── dashboard/      # React/Vite dashboard and local Node server
├── hardware/       # Raspberry Pi capture and actuator bridge
├── learner/        # onboarding profile and policy
├── ml/             # laptop FastAPI, chat, quiz, voice and TTS
├── persona/        # response personality
├── vision/         # laptop face detection and recognition
└── SIH2026-Presentation-HackTuah-TableTot.pptx
```

---

## Acknowledgements

- **Team:** HackTuah
- **Event:** Smart India Hackathon 2026
- **Problem Statement:** SIH26224 — Student Innovation
- **Theme:** Smart Education | **Category:** Hardware
