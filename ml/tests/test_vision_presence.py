"""
tests/test_vision_presence.py — Unit tests for presence smoothing.

Per-frame recognition is noisy: a blink, a turn of the head or a moment of
motion blur flips a single frame to the wrong answer. The tracker turns that
noisy per-frame stream into stable "student arrived" / "student left" events.

Run with: pytest tests/test_vision_presence.py -v
"""

import pytest

from vision.presence import PresenceEvent, PresenceTracker


@pytest.fixture
def tracker():
    return PresenceTracker(confirm_frames=3, forget_frames=5)


def _feed(tracker, value, times):
    """Push the same observation in several times, returning the last event."""
    event = None
    for _ in range(times):
        event = tracker.update(value)
    return event


class TestArrival:
    def test_starts_with_nobody_present(self, tracker):
        assert tracker.current is None

    def test_a_single_frame_does_not_confirm_anybody(self, tracker):
        assert tracker.update("asha") is None
        assert tracker.current is None

    def test_confirms_after_the_required_consecutive_frames(self, tracker):
        assert tracker.update("asha") is None
        assert tracker.update("asha") is None
        event = tracker.update("asha")
        assert event == PresenceEvent(kind="arrived", student_id="asha")
        assert tracker.current == "asha"

    def test_does_not_re_announce_a_student_already_present(self, tracker):
        _feed(tracker, "asha", 3)
        assert tracker.update("asha") is None
        assert tracker.update("asha") is None

    def test_a_one_frame_misidentification_cannot_confirm(self, tracker):
        """
        The whole point: two good frames plus one wrong frame must not let
        the wrong student through.
        """
        tracker.update("asha")
        tracker.update("asha")
        tracker.update("ravi")
        assert tracker.current is None

    def test_an_unrecognised_frame_breaks_the_streak(self, tracker):
        tracker.update("asha")
        tracker.update("asha")
        tracker.update(None)
        assert tracker.update("asha") is None
        assert tracker.current is None


class TestDeparture:
    def test_a_brief_glance_away_does_not_count_as_leaving(self, tracker):
        """Looking down at a book drops the face for a few frames. Stay put."""
        _feed(tracker, "asha", 3)
        for _ in range(4):
            assert tracker.update(None) is None
        assert tracker.current == "asha"

    def test_sustained_absence_reports_a_departure(self, tracker):
        _feed(tracker, "asha", 3)
        event = _feed(tracker, None, 5)
        assert event == PresenceEvent(kind="departed", student_id="asha")
        assert tracker.current is None

    def test_departure_is_reported_only_once(self, tracker):
        _feed(tracker, "asha", 3)
        _feed(tracker, None, 5)
        assert tracker.update(None) is None

    def test_absence_counter_resets_when_the_student_comes_back(self, tracker):
        _feed(tracker, "asha", 3)
        _feed(tracker, None, 4)
        tracker.update("asha")
        assert _feed(tracker, None, 4) is None
        assert tracker.current == "asha"


class TestHandover:
    def test_a_new_student_taking_the_desk_is_announced(self, tracker):
        _feed(tracker, "asha", 3)
        event = _feed(tracker, "ravi", 3)
        assert event == PresenceEvent(kind="arrived", student_id="ravi")
        assert tracker.current == "ravi"


class TestConfiguration:
    def test_confirm_frames_must_be_at_least_one(self):
        with pytest.raises(ValueError):
            PresenceTracker(confirm_frames=0, forget_frames=5)

    def test_a_single_confirm_frame_confirms_immediately(self):
        immediate = PresenceTracker(confirm_frames=1, forget_frames=5)
        assert immediate.update("asha") == PresenceEvent(
            kind="arrived", student_id="asha"
        )
