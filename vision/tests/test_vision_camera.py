"""
vision/tests/test_vision_camera.py — Tests for the camera front-end.

No real camera is used: a fake capture object is injected, which lets us test
the awkward parts — backend choice, warm-up, and transient read failures —
deterministically.

These exist because enrolment failed on the first real run with "camera
returned no frame". Measured on this machine:

    CAP_DSHOW  ->  14 frames in 3s   (works)
    CAP_MSMF   ->   1 frame          (stalls)
    CAP_ANY    ->   1 frame          (stalls; MSMF is the Windows default)

Run with: pytest vision/tests/test_vision_camera.py -v
"""

import cv2
import numpy as np
import pytest

from vision.camera import WebcamSource, preferred_backend


class FakeCapture:
    """
    Stands in for cv2.VideoCapture.

    ``script`` is the sequence of read() outcomes: True means a frame,
    False means a failed read. It repeats its last entry forever.
    """

    def __init__(self, script: list[bool], opened: bool = True) -> None:
        self._script = script
        self._opened = opened
        self.reads = 0
        self.released = False
        self.properties: dict[int, float] = {}

    def isOpened(self) -> bool:  # noqa: N802 - mirrors the OpenCV API
        return self._opened

    def set(self, prop: int, value: float) -> bool:  # noqa: A003
        self.properties[prop] = value
        return True

    def read(self):
        index = min(self.reads, len(self._script) - 1)
        self.reads += 1
        if self._script[index]:
            return True, np.zeros((480, 640, 3), dtype=np.uint8)
        return False, None

    def release(self) -> None:
        self.released = True


def _factory(capture):
    """Build a capture_factory that always hands back the given fake."""
    return lambda index, backend: capture


class TestBackendChoice:
    def test_windows_uses_directshow(self):
        """
        The Windows default (MSMF) delivered one frame and then stalled on the
        development machine; DirectShow works.
        """
        assert preferred_backend("win32") == cv2.CAP_DSHOW

    def test_other_platforms_let_opencv_choose(self):
        """The Pi runs Linux, where V4L2 via CAP_ANY is the right default."""
        assert preferred_backend("linux") == cv2.CAP_ANY


class TestOpening:
    def test_raises_a_useful_error_when_the_camera_will_not_open(self):
        capture = FakeCapture([True], opened=False)
        with pytest.raises(RuntimeError, match="could not open camera"):
            WebcamSource(0, capture_factory=_factory(capture))

    def test_requests_the_configured_resolution(self):
        capture = FakeCapture([True])
        WebcamSource(0, width=640, height=480, capture_factory=_factory(capture))
        assert capture.properties[cv2.CAP_PROP_FRAME_WIDTH] == 640
        assert capture.properties[cv2.CAP_PROP_FRAME_HEIGHT] == 480


class TestWarmUp:
    def test_discards_warm_up_frames_before_yielding_any(self):
        """
        The first frames off a webcam are black while exposure settles. A
        capture taken from them is useless for enrolment.
        """
        capture = FakeCapture([True])
        source = WebcamSource(0, warmup_frames=5, capture_factory=_factory(capture))
        next(iter(source.frames()))
        assert capture.reads == 6  # five discarded, then the one we took

    def test_survives_failed_reads_during_warm_up(self):
        """Cameras commonly fail the first few reads while starting up."""
        capture = FakeCapture([False, False, False, True])
        source = WebcamSource(0, warmup_frames=3, capture_factory=_factory(capture))
        assert next(iter(source.frames())) is not None


class TestTransientFailures:
    def test_a_single_failed_read_does_not_end_the_stream(self):
        """
        This is what broke enrolment: one failed read ended the generator, so
        the whole session collected zero frames.
        """
        capture = FakeCapture([True, False, True])
        source = WebcamSource(0, warmup_frames=0, capture_factory=_factory(capture))

        frames = []
        for frame in source.frames():
            frames.append(frame)
            if len(frames) == 2:
                break
        assert len(frames) == 2

    def test_gives_up_when_the_camera_really_is_gone(self):
        """Unplugged camera: stop rather than spin forever."""
        capture = FakeCapture([True, False], opened=True)
        source = WebcamSource(
            0, warmup_frames=0, max_read_retries=3, capture_factory=_factory(capture)
        )
        assert len(list(source.frames())) == 1

    def test_release_closes_the_camera(self):
        capture = FakeCapture([True])
        source = WebcamSource(0, warmup_frames=0, capture_factory=_factory(capture))
        source.release()
        assert capture.released is True
