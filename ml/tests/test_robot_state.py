from ml.robot_state import RobotState


def test_recognized_face_emits_one_arrival_and_happy_servo_command():
    state = RobotState(confirm_frames=3, forget_frames=2)

    assert state.observe_face(student_id="42", face_count=1)["event"] is None
    assert state.observe_face(student_id="42", face_count=1)["event"] is None
    arrived = state.observe_face(student_id="42", face_count=1)

    assert arrived["event"] == "arrived"
    assert arrived["student_id"] == "42"
    assert arrived["face_state"] == "happy"
    assert arrived["servo_state"] == "happy"
    assert state.observe_face(student_id="42", face_count=1)["event"] is None


def test_departure_is_debounced_and_returns_servos_to_idle():
    state = RobotState(confirm_frames=1, forget_frames=2)
    state.observe_face(student_id="asha", face_count=1)

    assert state.observe_face(student_id=None, face_count=0)["event"] is None
    departed = state.observe_face(student_id=None, face_count=0)

    assert departed["event"] == "departed"
    assert departed["student_id"] is None
    assert departed["servo_state"] == "idle"


def test_transient_greeting_expires_without_forgetting_student():
    clock = [10.0]
    state = RobotState(confirm_frames=1, now=lambda: clock[0])
    state.observe_face(student_id="7", face_count=1)

    clock[0] = 14.0
    command = state.command()

    assert command["face_state"] == "idle"
    assert command["servo_state"] == "idle"
    assert command["student_id"] == "7"
    assert command["student_present"] is True
