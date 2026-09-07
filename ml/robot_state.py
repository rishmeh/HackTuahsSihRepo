"""Laptop-owned state machine for the Table Tot peripheral bridge.

The Raspberry Pi reports observations and telemetry.  This module is the one
place that decides which expression and servo gesture the robot should show.
Keeping that decision on the laptop prevents the Pi's polling loop from
overwriting a face-recognition gesture with a stale ``idle`` command.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from time import monotonic
from typing import Callable, Optional


VALID_ROBOT_STATES = {
    "idle",
    "listening",
    "speaking",
    "thinking",
    "happy",
    "sleeping",
    "focus",
}


class RobotState:
    """Debounce face observations and expose versioned peripheral commands."""

    def __init__(
        self,
        *,
        confirm_frames: int = 3,
        forget_frames: int = 5,
        now: Callable[[], float] = monotonic,
    ) -> None:
        if confirm_frames < 1 or forget_frames < 1:
            raise ValueError("confirm_frames and forget_frames must be positive")
        self.confirm_frames = confirm_frames
        self.forget_frames = forget_frames
        self._now = now
        self._lock = RLock()
        self._candidate: Optional[str] = None
        self._candidate_frames = 0
        self._missing_frames = 0
        self._unknown_frames = 0
        self._revision = 0
        self._expires_at: Optional[float] = None
        self._command = {
            "face_state": "idle",
            "servo_state": "idle",
            "student_id": None,
            "student_present": False,
            "awaiting_face": False,
            "overlay_text": None,
            "overlay_duration": None,
        }
        self._telemetry: dict = {}

    def _set_command(self, **changes) -> None:
        changed = False
        for key, value in changes.items():
            if self._command.get(key) != value:
                self._command[key] = value
                changed = True
        if changed:
            self._revision += 1

    def _expire_transient_command(self) -> None:
        if self._expires_at is None or self._now() < self._expires_at:
            return
        self._expires_at = None
        self._set_command(
            face_state="idle",
            servo_state="idle",
            overlay_text=None,
            overlay_duration=None,
        )

    def observe_face(
        self,
        *,
        student_id: Optional[str],
        face_count: int,
        score: float = 0.0,
    ) -> dict:
        """Fold one recognition result into stable arrival/departure state."""
        del score  # retained in the public signature for logging/future policies
        with self._lock:
            self._expire_transient_command()
            event: Optional[str] = None
            current = self._command["student_id"]

            if student_id:
                self._missing_frames = 0
                self._unknown_frames = 0
                if current == student_id:
                    self._candidate = None
                    self._candidate_frames = 0
                else:
                    if self._candidate == student_id:
                        self._candidate_frames += 1
                    else:
                        self._candidate = student_id
                        self._candidate_frames = 1

                    if self._candidate_frames >= self.confirm_frames:
                        event = "arrived"
                        self._candidate = None
                        self._candidate_frames = 0
                        self._expires_at = self._now() + 3.0
                        self._set_command(
                            student_id=student_id,
                            student_present=True,
                            awaiting_face=False,
                            face_state="happy",
                            servo_state="happy",
                            overlay_text="Welcome back!",
                            overlay_duration=3.0,
                        )
            else:
                self._candidate = None
                self._candidate_frames = 0
                if current is not None:
                    self._missing_frames += 1
                    if self._missing_frames >= self.forget_frames:
                        event = "departed"
                        self._missing_frames = 0
                        self._expires_at = None
                        self._set_command(
                            student_id=None,
                            student_present=False,
                            awaiting_face=face_count > 0,
                            face_state="thinking" if face_count > 0 else "idle",
                            servo_state="thinking" if face_count > 0 else "idle",
                            overlay_text="Who are you?" if face_count > 0 else None,
                            overlay_duration=2.0 if face_count > 0 else None,
                        )
                elif face_count > 0:
                    self._unknown_frames += 1
                    if self._unknown_frames >= self.confirm_frames:
                        self._expires_at = self._now() + 2.0
                        self._set_command(
                            student_present=False,
                            awaiting_face=True,
                            face_state="thinking",
                            servo_state="thinking",
                            overlay_text="Who are you?",
                            overlay_duration=2.0,
                        )
                else:
                    self._unknown_frames = 0
                    if self._command["awaiting_face"]:
                        self._set_command(awaiting_face=False)

            state = self.command()
            state["event"] = event
            return state

    def motion(self, detected: bool) -> dict:
        with self._lock:
            if detected:
                self._set_command(awaiting_face=self._command["student_id"] is None)
            elif self._command["student_id"] is None:
                self._set_command(awaiting_face=False)
            return self.command()

    def control(
        self,
        *,
        face_state: Optional[str] = None,
        servo_state: Optional[str] = None,
        overlay_text: Optional[str] = None,
        overlay_duration: Optional[float] = None,
    ) -> dict:
        """Set an explicit laptop-side command, used by UI and integration tests."""
        with self._lock:
            if face_state is not None and face_state not in VALID_ROBOT_STATES:
                raise ValueError(f"invalid face_state {face_state!r}")
            if servo_state is not None and servo_state not in VALID_ROBOT_STATES:
                raise ValueError(f"invalid servo_state {servo_state!r}")
            changes = {}
            if face_state is not None:
                changes["face_state"] = face_state
            if servo_state is not None:
                changes["servo_state"] = servo_state
            if overlay_text is not None:
                changes["overlay_text"] = overlay_text
            if overlay_duration is not None:
                changes["overlay_duration"] = overlay_duration
                self._expires_at = self._now() + max(0.0, overlay_duration)
            self._set_command(**changes)
            return self.command()

    def update_telemetry(self, telemetry: dict) -> None:
        with self._lock:
            self._telemetry = deepcopy(telemetry)

    def command(self) -> dict:
        with self._lock:
            self._expire_transient_command()
            return {**deepcopy(self._command), "revision": self._revision}

    def status(self) -> dict:
        with self._lock:
            return {"command": self.command(), "telemetry": deepcopy(self._telemetry)}
