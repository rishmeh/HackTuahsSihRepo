"""
persona_setup/questions.py — The six conversational persona questions.

Each question is phrased for voice: short, clear options labelled A/B/C/D so
the user can say a letter OR a keyword and both are accepted.

The ``answer_map`` turns a raw STT transcript into the canonical value used by
the learner policy (e.g. "stories" → "narrative").
"""
from __future__ import annotations

QUESTIONS: list[dict] = [
    {
        "id": "explanation_format",
        "ask": (
            "Question one. How do you like things explained? "
            "Say A for stories and real-life examples, "
            "B for clear structured steps, "
            "C for a quick list of key facts, "
            "or D for questions that help you think it through yourself."
        ),
        "dimension": "explanation_format",
        "options": ["narrative", "structural", "concise", "socratic"],
        "answer_map": {
            "a": "narrative",   "story": "narrative",    "stories": "narrative",
            "example": "narrative", "examples": "narrative", "narrative": "narrative",
            "b": "structural",  "structure": "structural", "steps": "structural",
            "structured": "structural", "clear": "structural",
            "c": "concise",     "list": "concise",   "facts": "concise",
            "quick": "concise", "short": "concise",
            "d": "socratic",    "question": "socratic", "questions": "socratic",
            "think": "socratic", "socratic": "socratic", "myself": "socratic",
        },
    },
    {
        "id": "response_length",
        "ask": (
            "Question two. How long should my replies be? "
            "A for short and to the point — two or three sentences, "
            "B for a normal paragraph, "
            "or C for detailed explanations that always cover the why."
        ),
        "dimension": "response_length",
        "options": ["terse", "normal", "detailed"],
        "answer_map": {
            "a": "terse",    "short": "terse",    "brief": "terse",   "concise": "terse",
            "quick": "terse", "point": "terse",
            "b": "normal",   "normal": "normal",  "paragraph": "normal", "medium": "normal",
            "c": "detailed", "detailed": "detailed", "detail": "detailed",
            "long": "detailed", "everything": "detailed", "why": "detailed",
        },
    },
    {
        "id": "wrong_answer_style",
        "ask": (
            "Question three. When you get something wrong, how should I handle it? "
            "A — gently, with encouragement and warmth, "
            "B — straightforwardly with a clear correction, "
            "or C — analytically, exploring why that answer was tempting."
        ),
        "dimension": "wrong_answer_style",
        "options": ["gentle", "supportive", "analytical"],
        "answer_map": {
            "a": "gentle",     "gentle": "gentle",   "warm": "gentle",
            "encourage": "gentle", "encouragement": "gentle", "sensitive": "gentle",
            "b": "supportive", "supportive": "supportive", "clear": "supportive",
            "straightforward": "supportive", "direct": "supportive",
            "c": "analytical", "analytical": "analytical", "analyse": "analytical",
            "analyze": "analytical", "explore": "analytical", "why": "analytical",
        },
    },
    {
        "id": "persona_mode",
        "ask": (
            "Question four. How should I behave with you? "
            "A — like a teacher, guiding you step by step, "
            "B — like a peer, working through things together, "
            "C — like a Socratic mentor, asking questions to help you discover answers, "
            "or D — stay out of your way and only help when asked."
        ),
        "dimension": "persona_mode",
        "options": ["teacher", "peer", "socratic", "independent"],
        "answer_map": {
            "a": "teacher",     "teacher": "teacher",   "guide": "teacher",
            "guiding": "teacher", "step": "teacher",
            "b": "peer",        "peer": "peer",         "together": "peer",
            "friend": "peer",   "buddy": "peer",        "colleague": "peer",
            "c": "socratic",    "socratic": "socratic", "mentor": "socratic",
            "question": "socratic", "discover": "socratic",
            "d": "independent", "independent": "independent", "alone": "independent",
            "way": "independent", "quiet": "independent",
        },
    },
    {
        "id": "motivation",
        "ask": (
            "Question five. What motivates you most? "
            "A — pure curiosity and exploration, "
            "B — getting practical things done efficiently, "
            "C — filling in gaps in your knowledge, "
            "or D — mastering skills deeply."
        ),
        "dimension": "motivation",
        "options": ["curiosity", "utility", "gap", "mastery"],
        "answer_map": {
            "a": "curiosity",  "curiosity": "curiosity", "curious": "curiosity",
            "explore": "curiosity", "exploration": "curiosity",
            "b": "utility",    "utility": "utility",  "practical": "utility",
            "done": "utility", "efficient": "utility", "useful": "utility",
            "c": "gap",        "gap": "gap",          "gaps": "gap",
            "fill": "gap",     "knowledge": "gap",    "missing": "gap",
            "d": "mastery",    "mastery": "mastery",  "master": "mastery",
            "deep": "mastery", "deeply": "mastery",   "skill": "mastery",
        },
    },
    {
        "id": "tone",
        "ask": (
            "Last question. What tone do you prefer? "
            "A — playful and fun, with a bit of humour and banter, "
            "or B — professional and to the point, no banter."
        ),
        "dimension": "tone",
        "options": ["playful", "plain"],
        "answer_map": {
            "a": "playful",  "playful": "playful", "fun": "playful",
            "humor": "playful", "humour": "playful", "banter": "playful",
            "funny": "playful", "jokes": "playful",  "warm": "playful",
            "b": "plain",    "plain": "plain",  "professional": "plain",
            "serious": "plain", "formal": "plain", "efficient": "plain",
            "point": "plain",
        },
    },
]


def classify_answer(question: dict, raw: str) -> str | None:
    """
    Map a raw STT transcript to one of the question's canonical option values.
    Returns None if no keyword matches (caller should ask again).
    """
    raw_lower = raw.lower().strip()
    am = question["answer_map"]
    # Exact token match first
    for token, value in am.items():
        if token in raw_lower.split():
            return value
    # Substring match (longer tokens first to avoid false short matches)
    for token in sorted(am, key=len, reverse=True):
        if token in raw_lower:
            return am[token]
    return None
