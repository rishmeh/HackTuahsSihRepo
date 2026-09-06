# Learner — onboarding questionnaire → learner profile → Tot's behaviour

The student app shows a 10-scene story ("The Mysterious World"). Each choice
secretly measures one thing about how the student learns. The backend scores
the answers into a **LearnerProfile**, stores it, and derives **TotSettings** —
concrete decisions about how Tot should teach this particular child.

```
app  ──GET──>  /learner/questionnaire          the 10 scenes (no scoring data)
app  ──POST─>  /learner/{id}/answers           → profile + settings
tot  ──GET──>  /learner/{id}/settings          what to do for this student
```

Self-contained top-level package, like `vision/`. Mounted into `ml/main.py`.

## Setup

```bash
pip install -e .              # once, from the repo root
pytest learner/tests/ -q      # 94 tests
```

## Endpoints

| Method | Path | Who calls it | Returns |
|---|---|---|---|
| GET | `/learner/questionnaire` | student app | scenes, options — **never weights** |
| POST | `/learner/{id}/answers` | student app | `{profile, settings}` |
| GET | `/learner/{id}/profile` | dashboard | stored profile |
| GET | `/learner/{id}/settings` | Tot (chat, voice) | `TotSettings` |
| GET | `/learner/students` | dashboard | ids with a profile |
| DELETE | `/learner/{id}` | dashboard | erasure |

Submit body: `{"age": 12, "answers": {"1": "A", "2": "C", ...}}`. Skipped scenes
are omitted and score as *unknown*, never as a guess.

## Files

```
learner/
├── questionnaire.json   the 10 scenes + hidden per-option weights  ← edit wording here
├── questionnaire.py     loads/validates it; produces the public view
├── scoring.py           answers → LearnerProfile          (pure, 25 tests)
├── policy.py            LearnerProfile → TotSettings      (pure, 35 tests)
├── profile_store.py     SQLite, one row per student
├── routes.py            FastAPI router
├── models.py            LearnerProfile, TotSettings, AnswerSubmission
├── config.py            paths, sarcasm min age
└── tests/
```

## How scoring works

**Weights, never labels.** A profile never says "visual learner"; it says
`narrative 0.6 · structural 0.2 · concise 0.1 · socratic 0.1`, with a
confidence attached. A label is a verdict about a child. A weight is a
hypothesis that later evidence is allowed to move.

Three kinds of dimension:

| Kind | Shape | Example |
|---|---|---|
| Preference | distribution over values | explanation_format, persona_mode |
| Trait | scalar 0–1 | help_seeking, failure_sensitivity |
| Constraint | flag | Scene 10: brevity / explain_why / low_stakes / playful |

**Answers cross-load.** Scene 2A ("think hard myself") sets `help_seeking 0.1`
*and* `frustration_tolerance 0.8`. Scene 2D ("sit with it") sets `0.2` and
`0.95` — same low help-seeking, very different tolerance. One number would have
lost that.

**Corroboration → confidence.** Scenes 4 and 7 both measure format; 1 and 3
both measure how the student enters material; 5 and 6 both measure exposure
to failure.

| Sources | Confidence |
|---|---|
| two, agreeing | 1.0 |
| one | 0.7 |
| two, disagreeing | 0.5 |
| none | 0.0 |

Disagreement is information, not noise: the student has no stable preference
here, so a future bandit should explore freely.

**Age scaling.** Confidence × 0.6 under 9, × 0.8 for 9–12, × 1.0 for 13+. The
preference itself is never scaled — only how firmly it's held.

## How policy works

Decisions resolve in a fixed precedence:

```
1. child safety           (chat/safety_filter — absolute)
2. Scene 10 constraints   the student's own rule; never learned away
3. failure-derived gates  sarcasm off for a failure-sensitive child
4. learned values         from the bandit, later
5. questionnaire priors
6. defaults
```

**Playful ≠ sarcastic.** A student who says "make it fun" (10D) and also
"relieved it wasn't me" (6A) gets warmth and silliness, never irony at their
expense. Two separate settings, tested separately.

**The sarcasm gate fails closed** — off under 11, off when
`failure_sensitivity ≥ 0.6`, off under `low_stakes`. Every path is tested.

**Only three lines reach the SLM prompt** (format, length, wrong-answer style).
A 0.6B model cannot follow eleven style instructions; everything else —
hint timing, phrase pools, persona framing — is handled in code.

**Every non-default choice comes with a reason**, for the parent dashboard and
for anyone asking why.

## RL-ready

`encouragement_arms` is the set a bandit may choose among later. Constraints
**remove** arms from the set rather than penalising them — `low_stakes` deletes
`challenge` — so a learner can never explore into a forbidden action, not even
once. `derive_settings(profile, learned={...})` already accepts learned values;
they override priors and are refused if a constraint forbids them.

## Two things to know

- `learner/data/learner.db` holds the profiles. It's gitignored. `DELETE
  /learner/{id}` is a real erasure.
- This table is the first piece of the students database the implementation
  plan calls for. `student_id` is the key that will join it to face embeddings
  (`vision/`) and sessions.

## Dashboard wiring (student onboarding UI)

The student sees this questionnaire in `dashboard/` right after their first
login, as illustrated cards. The browser **never** calls this API directly:

```
browser ──tRPC──> dashboard/server/onboardingRouter.ts ──HTTP──> /learner/*
                  questionnaire → scenes only
                  status        → { completed }
                  submit        → { ok, answered }      ← profile & settings dropped here
```

`student_id` on this side is the dashboard's `profiles.id`. Set `ML_API_URL`
for the dashboard server if the ml API is not on `http://127.0.0.1:8000`.

UI: `dashboard/client/src/pages/Onboarding.tsx`, `components/onboarding/`.
Photos: `dashboard/client/public/onboarding/` (see `ATTRIBUTION.md` there).
