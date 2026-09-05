"""
vision/enrollment.py — Deciding when to grab an enrolment sample.

Enrolment originally asked the user to press SPACE in the preview window. That
failed in practice: OpenCV's window does not reliably hold keyboard focus on
Windows, and measured delivery was 0 of 10 presses with waitKey(1) and 1 of 10
with waitKey(30). It was also the wrong shape for the product — Table Tot is a
desk robot with a camera and a microphone, not a keyboard.

So enrolment is now on a timer: sit in front of the camera and it takes the
samples itself, spaced out so the student naturally shifts between them. That
spacing is not incidental. Six frames grabbed in one burst are six copies of a
single pose, which is what makes recognition brittle later.

The class holds no clock of its own — the caller passes the current time in.
That keeps the entire schedule unit-testable without sleeping.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TimedSampler:
    """
    Decides when the enrolment loop should keep a frame.

    Args:
        samples: How many frames to collect in total.
        interval: Minimum seconds between two captures.
        lead_in: Seconds to wait before the first capture, so the student has
            time to sit down and look at the camera.
        timeout: Seconds after which to give up. None means never. Samples are
            only taken while a face is visible, so without this an empty chair
            leaves the session running forever — which is exactly what happened
            on the first live run.
    """

    def __init__(
        self,
        samples: int = 6,
        interval: float = 1.5,
        lead_in: float = 2.0,
        timeout: float | None = 60.0,
    ) -> None:
        if samples < 1:
            raise ValueError("samples must be at least 1")
        if interval <= 0:
            raise ValueError("interval must be positive")
        if lead_in < 0:
            raise ValueError("lead_in cannot be negative")

        # The fastest possible run is the lead-in plus one interval per sample
        # after the first. A timeout below that could never succeed.
        minimum = lead_in + interval * (samples - 1)
        if timeout is not None and timeout < minimum:
            raise ValueError(
                f"timeout of {timeout}s is shorter than the {minimum}s this "
                f"schedule needs at best ({samples} samples every {interval}s "
                f"after a {lead_in}s lead-in)"
            )

        self.samples = samples
        self.interval = interval
        self.lead_in = lead_in
        self.timeout = timeout

        self.captured = 0
        # When the next capture becomes due. Before the first one this is the
        # lead-in; afterwards it moves forward by one interval each time.
        self._next_due = lead_in

    @property
    def done(self) -> bool:
        """True once every requested sample has been taken."""
        return self.captured >= self.samples

    def should_capture(self, now: float, face_present: bool) -> bool:
        """
        Decide whether to keep the current frame.

        Returns True at most once per interval, and only while a face is
        actually visible — a blank frame must never consume one of the samples.
        Calling this is what advances the schedule, so call it once per frame.

        Args:
            now: Seconds since the enrolment started.
            face_present: Whether the detector found a face in this frame.
        """
        if self.done or not face_present or now < self._next_due:
            return False

        self.captured += 1
        # Measure the next gap from now rather than from the due time, so a
        # student who looked away does not get a burst of catch-up captures.
        self._next_due = now + self.interval
        logger.info("Enrolment sample %d/%d captured", self.captured, self.samples)
        return True

    def expired(self, now: float) -> bool:
        """
        True when the session has run out of time without finishing.

        A completed sampler is never expired — finishing on the last second is
        success, not a timeout.
        """
        if self.done or self.timeout is None:
            return False
        return now >= self.timeout

    def seconds_until_next(self, now: float) -> float:
        """Countdown to the next capture, for display. Never negative."""
        return max(0.0, self._next_due - now)
