"""
vision/presence.py — Turning noisy per-frame recognition into stable events.

Recognition is run per frame, and per frame it is unreliable: a blink, a head
turn or motion blur will occasionally return the wrong student or no student
at all. Acting on a single frame gives a companion robot that greets the
student four times a minute and mistakes a sibling for them once an hour.

The tracker fixes that with two counters:

  * A student must be seen for ``confirm_frames`` consecutive frames before an
    "arrived" event fires. A one-frame misidentification can never win.
  * A confirmed student must be missing for ``forget_frames`` consecutive
    frames before "departed" fires, so glancing down at a book is not treated
    as leaving the desk.

This is pure state machine logic — no camera, no model — so the behaviour that
makes or breaks the live demo is fully unit tested.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

EventKind = Literal["arrived", "departed"]


@dataclass(frozen=True)
class PresenceEvent:
    """A confirmed change in who is at the desk."""

    kind: EventKind
    student_id: str


class PresenceTracker:
    """
    Smooths a stream of per-frame identities into arrival/departure events.

    Feed every frame's result to :meth:`update` — a student id when someone was
    recognised, or None when the frame had no face or an unknown one. The
    method returns an event on the frame where a change is confirmed, and None
    on every other frame.
    """

    def __init__(self, confirm_frames: int = 3, forget_frames: int = 5) -> None:
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be at least 1")
        if forget_frames < 1:
            raise ValueError("forget_frames must be at least 1")

        self.confirm_frames = confirm_frames
        self.forget_frames = forget_frames

        self._current: Optional[str] = None
        self._candidate: Optional[str] = None
        self._candidate_streak = 0
        self._absent_streak = 0

    @property
    def current(self) -> Optional[str]:
        """The student confirmed to be at the desk, or None."""
        return self._current

    def update(self, observed: Optional[str]) -> Optional[PresenceEvent]:
        """
        Record one frame's identity and return an event if presence changed.

        Args:
            observed: The recognised student id, or None for no/unknown face.
        """
        if observed is None:
            return self._on_absent_frame()
        return self._on_present_frame(observed)

    # -- internals ----------------------------------------------------------

    def _on_absent_frame(self) -> Optional[PresenceEvent]:
        # A missing face breaks any streak building towards a new arrival.
        self._candidate = None
        self._candidate_streak = 0

        if self._current is None:
            return None

        self._absent_streak += 1
        if self._absent_streak < self.forget_frames:
            return None

        departed = self._current
        self._current = None
        self._absent_streak = 0
        logger.info("Student %r left the desk", departed)
        return PresenceEvent(kind="departed", student_id=departed)

    def _on_present_frame(self, observed: str) -> Optional[PresenceEvent]:
        # Seeing anybody means the desk is not empty, so cancel any pending
        # departure — the student who looked down has looked back up.
        self._absent_streak = 0

        if observed == self._current:
            # Already confirmed and still here: nothing to announce.
            self._candidate = None
            self._candidate_streak = 0
            return None

        if observed == self._candidate:
            self._candidate_streak += 1
        else:
            self._candidate = observed
            self._candidate_streak = 1

        if self._candidate_streak < self.confirm_frames:
            return None

        self._current = observed
        self._candidate = None
        self._candidate_streak = 0
        logger.info("Student %r confirmed at the desk", observed)
        return PresenceEvent(kind="arrived", student_id=observed)
