"""
vision/camera.py — Live camera front-end for the vision pipeline.

The pipeline itself takes plain numpy frames and knows nothing about cameras.
This module is the only place that talks to hardware, which is what makes the
laptop-to-Raspberry-Pi move a one-class change: implement another FrameSource
backed by Picamera2 and nothing downstream notices.

Usage:

    python -m vision.camera enroll --student asha      # teach it a face
    python -m vision.camera watch                      # live recognition
    python -m vision.camera list                       # who is enrolled
    python -m vision.camera delete --student asha      # forget a student

Press q or ESC to quit either window. Enrolment captures on a timer -
just sit in front of the camera.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Iterator, Protocol

import cv2
import numpy as np

import config
from vision.enrollment import TimedSampler
from vision.factory import build_pipeline
from vision.pipeline import VisionPipeline

logger = logging.getLogger(__name__)

# Drawn in BGR, because that is the order OpenCV works in.
_GREEN = (0, 200, 0)
_AMBER = (0, 180, 255)
_GREY = (150, 150, 150)


class FrameSource(Protocol):
    """Anything that can hand out camera frames as BGR numpy arrays."""

    def frames(self) -> Iterator[np.ndarray]: ...

    def release(self) -> None: ...


def preferred_backend(platform: str | None = None) -> int:
    """
    Pick the OpenCV capture backend for this platform.

    On Windows the default is Media Foundation, which on the development
    machine opened the camera, produced exactly one frame and then stalled.
    DirectShow delivered frames continuously against the same hardware, so
    Windows is pinned to it. Everywhere else — the Raspberry Pi included —
    OpenCV's own choice (V4L2 on Linux) is correct.
    """
    platform = platform if platform is not None else sys.platform
    return cv2.CAP_DSHOW if platform == "win32" else cv2.CAP_ANY


class WebcamSource:
    """
    A laptop webcam via cv2.VideoCapture — the development front-end.

    On the Raspberry Pi, write a PicameraSource with the same two methods and
    pass that instead; nothing else in the codebase changes.

    Args:
        index: Camera index.
        width, height: Requested capture resolution.
        warmup_frames: Frames to read and throw away before yielding any. A
            webcam's first frames are black while exposure settles, and an
            enrolment sample taken from one of those is worthless.
        max_read_retries: Consecutive failed reads tolerated before giving up.
            Cameras hiccup; treating the first failure as fatal ended enrolment
            sessions with zero frames collected.
        capture_factory: Injection point for tests. Called as
            factory(index, backend).
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 640,
        height: int = 480,
        warmup_frames: int = 20,
        max_read_retries: int = 15,
        capture_factory=cv2.VideoCapture,
    ) -> None:
        self.index = index
        self.warmup_frames = warmup_frames
        self.max_read_retries = max_read_retries

        self._capture = capture_factory(index, preferred_backend())
        if not self._capture.isOpened():
            raise RuntimeError(
                f"could not open camera {index}. Is another app using it "
                "(Teams, Zoom, the Camera app), or is CAMERA_INDEX wrong?"
            )
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def frames(self) -> Iterator[np.ndarray]:
        """
        Yield camera frames until the camera stops responding.

        Warm-up read failures are ignored entirely — a camera that is still
        starting up routinely fails its first few reads.
        """
        for _ in range(self.warmup_frames):
            self._capture.read()

        failures = 0
        while True:
            ok, frame = self._capture.read()
            if ok and frame is not None:
                failures = 0
                yield frame
                continue

            failures += 1
            if failures >= self.max_read_retries:
                logger.warning(
                    "camera returned no frame %d times in a row; stopping", failures
                )
                return

    def release(self) -> None:
        self._capture.release()


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _annotate(frame: np.ndarray, result, fps: float) -> np.ndarray:
    """Draw the box, the identity and the score onto a copy of the frame."""
    canvas = frame.copy()

    if result.face is not None:
        face = result.face
        matched = result.student_id is not None
        colour = _GREEN if matched else _AMBER
        label = (
            f"{result.student_id}  {result.score:.2f}"
            if matched
            else f"unknown  {result.score:.2f}"
        )
        cv2.rectangle(
            canvas,
            (face.x, face.y),
            (face.x + face.width, face.y + face.height),
            colour,
            2,
        )
        cv2.putText(
            canvas,
            label,
            (face.x, max(20, face.y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            colour,
            2,
        )

        # The five landmarks SFace aligns on — useful to see while debugging.
        if face.raw is not None:
            for i in range(4, 14, 2):
                cv2.circle(
                    canvas, (int(face.raw[i]), int(face.raw[i + 1])), 2, _GREEN, -1
                )

    cv2.putText(
        canvas,
        f"{fps:4.1f} fps",
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        _GREY,
        1,
    )
    return canvas


def _draw_enrol_overlay(
    frame: np.ndarray, face, sampler: TimedSampler, now: float, flash_until: float
) -> np.ndarray:
    """
    Draw the enrolment preview: face box, progress, and a countdown.

    The countdown matters — without it a timed capture feels broken, because
    the student cannot tell whether anything is about to happen.
    """
    preview = frame.copy()
    height, width = preview.shape[:2]

    if face is not None:
        cv2.rectangle(
            preview,
            (face.x, face.y),
            (face.x + face.width, face.y + face.height),
            _GREEN,
            2,
        )

    # A white flash frames the moment of capture, so it is obvious it happened.
    if now < flash_until:
        cv2.rectangle(preview, (0, 0), (width - 1, height - 1), (255, 255, 255), 12)

    cv2.putText(
        preview,
        f"captured {sampler.captured}/{sampler.samples}",
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        _GREEN,
        2,
    )

    if face is None:
        message, colour = "no face - move into the light", _AMBER
    elif sampler.done:
        message, colour = "done!", _GREEN
    else:
        message = f"next in {sampler.seconds_until_next(now):.1f}s"
        colour = _GREEN
    cv2.putText(
        preview, message, (10, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, colour, 2
    )
    return preview


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def watch(pipeline: VisionPipeline, source: FrameSource) -> None:
    """Live recognition, printing presence events as they are confirmed."""
    if not pipeline.enrolled_students:
        print(
            "Nobody is enrolled yet — run: "
            "python -m vision.camera enroll --student <name>"
        )
    else:
        print(f"Enrolled: {', '.join(pipeline.enrolled_students)}")
    print("Watching. Press q to quit.\n")

    last = time.perf_counter()
    fps = 0.0

    for frame in source.frames():
        result = pipeline.identify(frame)
        event = pipeline.tracker.update(result.student_id)

        if event is not None:
            verb = "sat down at" if event.kind == "arrived" else "left"
            print(f"  [{time.strftime('%H:%M:%S')}] {event.student_id} {verb} the desk")

        now = time.perf_counter()
        # Exponential smoothing, so the number does not jitter every frame.
        fps = 0.9 * fps + 0.1 / max(now - last, 1e-6)
        last = now

        cv2.imshow("Table Tot - vision", _annotate(frame, result, fps))
        # 20 ms, not 1 ms: the window needs time to pump its event queue or
        # keypresses are dropped (measured: 0 of 10 registered at 1 ms).
        if (cv2.waitKey(20) & 0xFF) in (ord("q"), 27):
            break


def enroll(
    pipeline: VisionPipeline,
    source: FrameSource,
    student_id: str,
    samples: int,
    interval: float = 1.5,
    lead_in: float = 3.0,
    timeout: float = 90.0,
) -> None:
    """
    Capture several frames of one student and store their embeddings.

    Capture is on a timer rather than a keypress. The preview window does not
    reliably hold keyboard focus (measured: 0 of 10 SPACE presses registered),
    and a desk robot has no keyboard anyway — so just sit there and it collects
    the samples itself.

    The samples are deliberately spaced a second or more apart. Six frames
    grabbed in one burst are six copies of one pose, and a student enrolled
    that way is only recognised sitting exactly as they did at enrolment.
    """
    print(f"Enrolling {student_id!r} — {samples} samples, one every {interval:g}s.")
    print(f"Sit facing the camera. First capture in {lead_in:g} seconds.")
    print("Between captures, turn your head a little and shift position.")
    print("Press q or ESC in the window to abort.\n")

    captured: list[np.ndarray] = []
    sampler = TimedSampler(
        samples=samples, interval=interval, lead_in=lead_in, timeout=timeout
    )
    started = time.perf_counter()
    flash_until = 0.0

    for frame in source.frames():
        now = time.perf_counter() - started
        face = pipeline.detector.detect_largest(frame)

        if sampler.should_capture(now, face_present=face is not None):
            captured.append(frame.copy())
            flash_until = now + 0.25
            print(f"  captured {sampler.captured}/{samples}")

        preview = _draw_enrol_overlay(frame, face, sampler, now, flash_until)
        cv2.imshow("Table Tot - enrol", preview)

        if sampler.done:
            cv2.waitKey(400)  # let the last frame stay on screen briefly
            break

        if sampler.expired(now):
            print(
                f"\nGave up after {timeout:g}s with "
                f"{sampler.captured}/{samples} samples — no face was visible "
                "for long enough. Sit facing the camera and try again."
            )
            if not captured:
                return
            print("Enrolling with what was captured.")
            break

        # 20 ms rather than 1 ms: the window needs time to pump its event
        # queue, and this also caps the loop at a sane rate.
        if (cv2.waitKey(20) & 0xFF) in (ord("q"), 27):
            print("Aborted; nothing was saved.")
            return

    result = pipeline.enroll(student_id, captured)
    print(
        f"\nEnrolled {result.student_id}: "
        f"{result.embeddings_added} new embedding(s), "
        f"{result.embeddings_total} total, "
        f"{result.frames_rejected} frame(s) rejected."
    )
    print("No images were saved — only the embedding vectors.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)

    parser = argparse.ArgumentParser(
        description="Table Tot face detection / recognition"
    )
    parser.add_argument("command", choices=["watch", "enroll", "list", "delete"])
    parser.add_argument("--student", help="Student id, for enroll and delete")
    parser.add_argument(
        "--samples", type=int, default=6, help="Frames to capture when enrolling"
    )
    parser.add_argument(
        "--interval", type=float, default=1.5, help="Seconds between enrolment captures"
    )
    parser.add_argument(
        "--timeout", type=float, default=90.0,
        help="Give up enrolling after this many seconds",
    )
    parser.add_argument("--camera", type=int, default=config.CAMERA_INDEX)
    args = parser.parse_args(argv)

    pipeline = build_pipeline()

    if args.command == "list":
        students = pipeline.enrolled_students
        print("Enrolled students:" if students else "Nobody is enrolled yet.")
        for student in students:
            print(f"  {student}  ({pipeline.store.count_embeddings(student)} embeddings)")
        return 0

    if args.command == "delete":
        if not args.student:
            parser.error("delete needs --student")
        removed = pipeline.store.delete_student(args.student)
        pipeline.reload_gallery()
        print(f"Removed {removed} embedding(s) for {args.student!r}.")
        return 0

    source = WebcamSource(args.camera)
    try:
        if args.command == "enroll":
            if not args.student:
                parser.error("enroll needs --student")
            enroll(
                pipeline, source, args.student, args.samples, args.interval,
                timeout=args.timeout,
            )
        else:
            watch(pipeline, source)
    finally:
        source.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
