# Persona — what Tot says, and how it sounds

Tot's personality, driven by each student's `TotSettings` from the `learner/`
package. Friendly, encouraging, occasionally dry — and never at a child's
expense.

```
SLM   →  the CONTENT   the answer itself
code  →  the VIBE      greeting · encouragement · celebration · sign-off
```

That split is the whole design. `qwen3:0.6b` cannot hold a consistent tone,
and asking any small model to "be sarcastic" is how a child gets mocked. So
the personality lives in **phrase pools written by a person**, chosen by the
student's settings and the moment. The model gets at most **three** plain
style directives.

## Files

```
persona/
├── phrases.py    the pools: 8 kinds × 4 arms, plus wrong-answer lines by style
├── prompt.py     persona block for the SLM system prompt (never weakens the rules)
├── decorate.py   wraps an answer in the right opener/closer for the moment
├── voice.py      settings → Piper pace (length_scale) and expressiveness
├── config.py     persona name, default Piper voice
└── tests/        40 tests, no model or audio needed
```

## Where it plugs in

**Chat** — [ml/chat/pipeline.py](../ml/chat/pipeline.py) looks up the student's
settings (or the safe default), composes the persona onto the system prompt,
and decorates the answer **before** the safety filter runs. `ChatRequest`
gained two optional fields:

```json
{ "query": "...", "student": {...}, "student_id": "asha", "situation": "wrong_answer" }
```

`situation` ∈ `question · correct_answer · wrong_answer · struggling ·
repeated_question · idle · greeting` — tells the decorator what moment this is.

**Voice** — `voice_agent.py` uses the pools for its spoken filler lines and
passes `voice_params(settings).synthesis_kwargs()` to Piper.

## The sarcasm rule, enforced in code

| Condition | Result |
|---|---|
| `settings.sarcasm_allowed` is False | no sarcastic phrase, ever |
| Situation is `wrong_answer` or `struggling` | no sarcastic phrase, even when allowed |
| Situation is `repeated_question`, `idle`, `error` **and** allowed | a dry line may appear |
| Student has no profile yet | default settings — sarcasm off |

A sarcastic phrase is tagged as such in the pool. Nothing infers tone from
text; nothing asks the model. Tests hammer every path 100–200 times.

> "Fourth time on this one. The topic's getting suspicious." — allowed, points at the situation.
> Anything pointed at a wrong answer — unreachable by construction.

## The four arms

The encouragement arms are the choices a bandit will later learn among, so
they must sound different (a test checks the vocabulary):

| Arm | Character | Example |
|---|---|---|
| warm | reassures | *"You've got this. Take your time."* |
| playful | lifts the mood | *"Plot twist: you're closer than you think!"* |
| challenge | dares | *"Bet you can crack this without a hint."* |
| plain | efficient, no exclamation marks | *"Keep going. You are close."* |

## Two rules that override everything

- A **terse** student (Scene 10A) gets the bare answer — except on a wrong
  answer, where the gentle line is not optional. Brevity is a preference;
  kindness on failure is not.
- The persona block **replaces only the identity preamble** of the chat prompt.
  `compose_system_prompt` refuses a base prompt with no `STRICT RULES` section,
  so the safety rules cannot be dropped by accident.

## Adding or editing lines

Edit the pools in `phrases.py`. Keep every phrase on one line, keep the plain
arm free of exclamation marks, and tag anything ironic with `True`. Run
`pytest persona/tests/ -q` — the coverage tests will tell you if a kind/arm
pool dropped below three lines.
