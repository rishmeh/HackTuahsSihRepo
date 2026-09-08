"""
persona_setup/questions.py — The ten conversational persona questions.

Each question is phrased for voice: short, clear options labelled A/B/C/D so
the user can say a letter OR a keyword and both are accepted.

The ``answer_map`` turns a raw STT transcript into the canonical option key
("A", "B", "C", "D") matching the options in `learner/questionnaire.json`.
"""
from __future__ import annotations

QUESTIONS: list[dict] = [
    {
        "id": 1,
        "ask": (
            "Question one. In a mysterious world, where do you want to go first? "
            "Say A for the tall tower, B for the forest, C for the village, or D straight to the question mark."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "tower": "A", "top": "A", "tall": "A",
            "b": "B", "forest": "B", "trees": "B",
            "c": "C", "village": "C", "people": "C",
            "d": "D", "question": "D", "mark": "D", "straight": "D",
        },
    },
    {
        "id": 2,
        "ask": (
            "Question two. A large stone blocks the path with a riddle. What do you do? "
            "Say A to think hard and answer yourself, B to ask for a small hint, "
            "C to ask me for the answer, or D to sit with it for a while."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "think": "A", "myself": "A", "hard": "A",
            "b": "B", "hint": "B", "small": "B",
            "c": "C", "answer": "C", "tell": "C",
            "d": "D", "sit": "D", "wait": "D", "while": "D",
        },
    },
    {
        "id": 3,
        "ask": (
            "Question three. Villagers want to teach you how to make lanterns. How do you want to learn? "
            "Say A to watch someone make one first, B to just figure it out yourself, "
            "C to be told the steps one by one, or D to make one together with a guide."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "watch": "A", "first": "A",
            "b": "B", "figure": "B", "yourself": "B", "materials": "B",
            "c": "C", "steps": "C", "told": "C", "one": "C",
            "d": "D", "together": "D", "guide": "D",
        },
    },
    {
        "id": 4,
        "ask": (
            "Question four. A storyteller offers to tell you about the world. How do you want to hear it? "
            "Say A for a story with characters, B for a map with explanations, "
            "C for a list of key facts, or D for her to just answer your questions."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "story": "A", "characters": "A",
            "b": "B", "map": "B", "explanations": "B",
            "c": "C", "list": "C", "facts": "C",
            "d": "D", "questions": "D", "answer": "D", "just": "D",
        },
    },
    {
        "id": 5,
        "ask": (
            "Question five. A wizard asks a riddle and you know the answer. What do you do? "
            "Say A to shout it out right away, B to raise your hand, "
            "C to wait to see if anyone else answers, or D to stay quiet."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "shout": "A", "right": "A", "away": "A",
            "b": "B", "raise": "B", "hand": "B",
            "c": "C", "wait": "C", "anyone": "C", "else": "C",
            "d": "D", "stay": "D", "quiet": "D", "keep": "D", "myself": "D",
        },
    },
    {
        "id": 6,
        "ask": (
            "Question six. Someone answers confidently but gets it completely wrong. How do you feel? "
            "Say A relieved it wasn't you, B curious why they thought that, "
            "C feel a little bad for them, or D glad because mistakes help us learn."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "relieved": "A", "wasn't": "A", "me": "A",
            "b": "B", "curious": "B", "why": "B",
            "c": "C", "bad": "C", "feel": "C",
            "d": "D", "glad": "D", "mistakes": "D", "learn": "D",
        },
    },
    {
        "id": 7,
        "ask": (
            "Question seven. You can take one book from the wizard's library. Which do you pick? "
            "Say A for a book of maps and diagrams, B for a book of stories about travelers, "
            "C for a book of answers to common questions, or D for a book that asks you questions."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "maps": "A", "diagrams": "A",
            "b": "B", "stories": "B", "travelers": "B", "travellers": "B",
            "c": "C", "answers": "C", "common": "C",
            "d": "D", "questions": "D", "asks": "D",
        },
    },
    {
        "id": 8,
        "ask": (
            "Question eight. What kind of companion do you want for the journey? "
            "Say A for someone who knows the way and guides you, B for someone to figure things out with together, "
            "C for someone who asks questions to help you think, or D you'd rather go alone."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "knows": "A", "way": "A", "guides": "A", "teacher": "A",
            "b": "B", "together": "B", "figure": "B", "peer": "B",
            "c": "C", "asks": "C", "questions": "C", "think": "C", "socratic": "C",
            "d": "D", "alone": "D", "pace": "D", "independent": "D",
        },
    },
    {
        "id": 9,
        "ask": (
            "Question nine. In a room full of things to learn, what do you pick first? "
            "Say A for something you're curious about, B for something useful, "
            "C for something you've struggled with, or D for something you want to master deeply."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "curious": "A", "curiosity": "A",
            "b": "B", "useful": "B", "utility": "B",
            "c": "C", "struggled": "C", "struggle": "C", "fix": "C", "gap": "C",
            "d": "D", "master": "D", "deeply": "D", "deeper": "D",
        },
    },
    {
        "id": 10,
        "ask": (
            "Last question. What should I never do when helping you? "
            "Say A talk too much, B skip the explanation, C make it feel like a test, or D be too serious."
        ),
        "options": ["A", "B", "C", "D"],
        "answer_map": {
            "a": "A", "talk": "A", "much": "A", "point": "A",
            "b": "B", "skip": "B", "explanation": "B", "why": "B",
            "c": "C", "test": "C", "relaxed": "C",
            "d": "D", "serious": "D", "fun": "D",
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
