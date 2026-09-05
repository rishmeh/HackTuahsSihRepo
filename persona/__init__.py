"""
persona/ — Tot's personality: what it says, and how it sounds.

Split on purpose:

    SLM   → the CONTENT   the actual answer to the student's question
    code  → the VIBE      greetings, encouragement, celebrations, sign-offs

A 0.6B language model cannot hold a consistent tone, and asking it to "be
sarcastic" is how a child gets mocked. So the personality lives in curated
phrase pools (phrases.py) chosen by the student's TotSettings, and the model
receives at most three plain style directives (prompt.py). Voice pace follows
the same settings (voice.py). decorate.py wraps an answer in the chosen lines.

Everything here is pure: no model, no audio hardware, all unit tested.
"""
