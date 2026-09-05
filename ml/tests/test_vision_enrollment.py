"""
tests/test_vision_enrollment.py — Tests for automatic enrolment sampling.

Enrolment used to require pressing SPACE in the OpenCV preview window. That
turned out to be unreliable — the window rarely holds keyboard focus on
Windows, and measured key delivery was 0/10 presses with waitKey(1) and 1/10
with waitKey(30). It was also the wrong design for a robot that has no
keyboard at all.

The sampler replaces it: it decides when to capture based on elapsed time and
whether a face is currently visible. Time is injected rather than read from
the clock, so the whole schedule is testable instantly and deterministically.

Run with: pytest tests/test_vision_enrollment.py -v
"""

import pytest

from vision.enrollment import TimedSampler


@pytest.fixture
def sampler():
    """Six samples, one every 1.5s, after a 2s lead-in to get settled."""
    return TimedSampler(samples=6, interval=1.5, lead_in=2.0)


class TestLeadIn:
    def test_does_not_capture_immediately(self, sampler):
        """The student needs a moment to sit down and look up."""
        assert sampler.should_capture(now=0.0, face_present=True) is False

    def test_does_not_capture_before_the_lead_in_elapses(self, sampler):
        assert sampler.should_capture(now=1.9, face_present=True) is False

    def test_captures_once_the_lead_in_has_elapsed(self, sampler):
        assert sampler.should_capture(now=2.0, face_present=True) is True


class TestFaceGating:
    def test_never_captures_a_frame_with_no_face(self, sampler):
        """A blank frame must not consume one of the six samples."""
        assert sampler.should_capture(now=5.0, face_present=False) is False

    def test_captures_as_soon_as_the_face_returns(self, sampler):
        assert sampler.should_capture(now=5.0, face_present=False) is False
        assert sampler.should_capture(now=5.1, face_present=True) is True


class TestSpacing:
    def test_waits_a_full_interval_between_captures(self, sampler):
        assert sampler.should_capture(now=2.0, face_present=True) is True
        assert sampler.should_capture(now=2.5, face_present=True) is False
        assert sampler.should_capture(now=3.4, face_present=True) is False
        assert sampler.should_capture(now=3.5, face_present=True) is True

    def test_spacing_exists_so_the_samples_are_not_identical(self, sampler):
        """
        Six frames grabbed in one burst would be six copies of one pose, which
        is exactly what makes recognition brittle. The gap gives the student
        time to shift.
        """
        captured = [
            t / 10
            for t in range(0, 200)
            if sampler.should_capture(now=t / 10, face_present=True)
        ]
        gaps = [b - a for a, b in zip(captured, captured[1:])]
        assert all(gap >= 1.5 - 1e-9 for gap in gaps)


class TestCompletion:
    def test_reports_progress(self, sampler):
        assert sampler.captured == 0
        sampler.should_capture(now=2.0, face_present=True)
        assert sampler.captured == 1

    def test_is_not_done_until_every_sample_is_taken(self, sampler):
        assert sampler.done is False
        for i in range(5):
            sampler.should_capture(now=2.0 + i * 1.5, face_present=True)
        assert sampler.done is False

    def test_is_done_after_the_last_sample(self, sampler):
        for i in range(6):
            sampler.should_capture(now=2.0 + i * 1.5, face_present=True)
        assert sampler.done is True

    def test_stops_capturing_once_done(self, sampler):
        for i in range(6):
            sampler.should_capture(now=2.0 + i * 1.5, face_present=True)
        assert sampler.should_capture(now=100.0, face_present=True) is False

    def test_reports_seconds_until_the_next_capture(self, sampler):
        assert sampler.seconds_until_next(now=0.0) == pytest.approx(2.0)
        sampler.should_capture(now=2.0, face_present=True)
        assert sampler.seconds_until_next(now=2.5) == pytest.approx(1.0)

    def test_countdown_never_goes_negative(self, sampler):
        assert sampler.seconds_until_next(now=99.0) == pytest.approx(0.0)


class TestConfiguration:
    def test_requires_at_least_one_sample(self):
        with pytest.raises(ValueError):
            TimedSampler(samples=0, interval=1.5, lead_in=2.0)

    def test_requires_a_positive_interval(self):
        with pytest.raises(ValueError):
            TimedSampler(samples=6, interval=0, lead_in=2.0)


class TestTimeout:
    """
    Enrolment must not spin forever when nobody is in front of the camera.

    A real run hung indefinitely because the sampler only captures while a
    face is visible, and the loop had no upper bound — so an empty chair meant
    an endless session.
    """

    def test_does_not_expire_before_the_timeout(self):
        sampler = TimedSampler(samples=6, interval=1.5, lead_in=2.0, timeout=30.0)
        assert sampler.expired(now=29.9) is False

    def test_expires_once_the_timeout_passes(self):
        sampler = TimedSampler(samples=6, interval=1.5, lead_in=2.0, timeout=30.0)
        assert sampler.expired(now=30.0) is True

    def test_never_expires_when_no_timeout_is_set(self):
        sampler = TimedSampler(samples=6, interval=1.5, lead_in=2.0, timeout=None)
        assert sampler.expired(now=10_000.0) is False

    def test_a_completed_sampler_is_not_treated_as_expired(self):
        """Finishing on the last second is success, not a timeout."""
        sampler = TimedSampler(samples=1, interval=1.5, lead_in=0.0, timeout=30.0)
        sampler.should_capture(now=0.0, face_present=True)
        assert sampler.done is True
        assert sampler.expired(now=100.0) is False

    def test_rejects_a_timeout_shorter_than_the_schedule_needs(self):
        """6 samples at 1.5s after a 2s lead-in cannot finish inside 5s."""
        with pytest.raises(ValueError, match="timeout"):
            TimedSampler(samples=6, interval=1.5, lead_in=2.0, timeout=5.0)
