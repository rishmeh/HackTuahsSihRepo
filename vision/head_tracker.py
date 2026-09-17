"""
vision/head_tracker.py — Convert a detected face bounding box into servo pan/tilt angles.

The face centre offset from the frame centre is mapped to degrees using the
camera's field of view.  The result is two angles that the Pi servo controller
can apply directly to keep the robot's head pointed at the user.

    pan  > 0 → face is to the RIGHT   → head turns right
    pan  < 0 → face is to the LEFT    → head turns left
    tilt > 0 → face is ABOVE centre   → head tilts up
    tilt < 0 → face is BELOW centre   → head tilts down

Default FOV values are for the Raspberry Pi Camera Module v2
(IMX219, 3280×2464 sensor), which gives:
    Horizontal FOV ≈ 62.2°   Vertical FOV ≈ 48.8°

If you use the Pi Camera Module v3 (IMX708) change to:
    h_fov_deg=66.0, v_fov_deg=41.0

A USB webcam is typically around:
    h_fov_deg=60.0, v_fov_deg=45.0
"""

from __future__ import annotations

from vision.models import FaceBox

# ---------------------------------------------------------------------------
# Pi Camera Module v2 field-of-view constants (degrees)
# ---------------------------------------------------------------------------
_PI_CAM_V2_H_FOV = 62.2
_PI_CAM_V2_V_FOV = 48.8


def face_to_servo_angles(
    face: FaceBox,
    frame_width: int,
    frame_height: int,
    h_fov_deg: float = _PI_CAM_V2_H_FOV,
    v_fov_deg: float = _PI_CAM_V2_V_FOV,
    pan_limit: float = 45.0,
    tilt_limit: float = 45.0,
) -> tuple[float, float]:
    """
    Map a detected face position to pan/tilt servo angles (degrees).

    Args:
        face:         Detected face bounding box from YuNet.
        frame_width:  Width of the camera frame in pixels.
        frame_height: Height of the camera frame in pixels.
        h_fov_deg:    Camera horizontal field of view in degrees.
        v_fov_deg:    Camera vertical field of view in degrees.
        pan_limit:    Maximum pan angle in either direction (degrees).
        tilt_limit:   Maximum tilt angle in either direction (degrees).

    Returns:
        (pan_deg, tilt_deg) — both clamped to ±limit.
        Positive pan  → face is right of centre → turn right.
        Positive tilt → face is above centre   → tilt up.
    """
    # Face centre in pixel space
    face_cx = face.x + face.width / 2.0
    face_cy = face.y + face.height / 2.0

    # Normalised offset from frame centre: range [-0.5, 0.5]
    norm_x = (face_cx - frame_width / 2.0) / frame_width
    norm_y = (face_cy - frame_height / 2.0) / frame_height

    # Convert normalised offset to degrees
    pan_deg = norm_x * h_fov_deg
    # y increases downward in pixel space; flip so tilt > 0 means "up"
    tilt_deg = -norm_y * v_fov_deg

    # Clamp to servo mechanical limits
    pan_deg = max(-pan_limit, min(pan_limit, pan_deg))
    tilt_deg = max(-tilt_limit, min(tilt_limit, tilt_deg))

    return round(pan_deg, 2), round(tilt_deg, 2)


def no_face_angles() -> tuple[float, float]:
    """Return neutral (centre) angles when no face is detected."""
    return 0.0, 0.0
