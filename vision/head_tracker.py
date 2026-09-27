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


class HeadTracker:
    """
    Stateful, smoothed head-tracker.

    Applies an Exponential Moving Average (EMA) to the raw pan/tilt angles
    computed from each frame so that the servo glides to its target rather
    than snapping there instantly.  When no face is detected the tracker
    holds (and continues to decay toward) the last known position — it does
    NOT snap back to 0°, which is the primary cause of visible jitter.

    Parameters
    ----------
    alpha_face   EMA weight for frames WITH a face (0 < α ≤ 1).
                 Higher = faster response, more jitter. Lower = smoother,
                 more lag.  0.25 feels snappy but not twitchy.
    alpha_nf     EMA weight for frames WITHOUT a face (very small so the
                 head drifts gently back toward centre rather than jumping).
    dead_zone    Face offset in degrees below which the servo is not moved
                 (prevents micro-corrections from sensor noise).
    """

    def __init__(
        self,
        alpha_face: float = 0.25,
        alpha_nf: float = 0.04,
        dead_zone: float = 1.5,
    ) -> None:
        self._alpha_face = alpha_face
        self._alpha_nf = alpha_nf
        self._dead_zone = dead_zone
        self._pan: float = 0.0
        self._tilt: float = 0.0

    def update_with_face(
        self,
        face: FaceBox,
        frame_width: int,
        frame_height: int,
        h_fov_deg: float = _PI_CAM_V2_H_FOV,
        v_fov_deg: float = _PI_CAM_V2_V_FOV,
        pan_limit: float = 45.0,
        tilt_limit: float = 45.0,
    ) -> tuple[float, float]:
        """Compute new EMA-smoothed angles from a detected face."""
        face_cx = face.x + face.width / 2.0
        face_cy = face.y + face.height / 2.0

        norm_x = (face_cx - frame_width / 2.0) / frame_width
        norm_y = (face_cy - frame_height / 2.0) / frame_height

        raw_pan  =  norm_x * h_fov_deg
        raw_tilt = -norm_y * v_fov_deg  # flip: pixel-y down → servo-tilt up

        raw_pan  = max(-pan_limit,  min(pan_limit,  raw_pan))
        raw_tilt = max(-tilt_limit, min(tilt_limit, raw_tilt))

        # Dead-zone: skip tiny corrections that just cause chatter
        if abs(raw_pan  - self._pan)  > self._dead_zone:
            self._pan  = self._pan  + self._alpha_face * (raw_pan  - self._pan)
        if abs(raw_tilt - self._tilt) > self._dead_zone:
            self._tilt = self._tilt + self._alpha_face * (raw_tilt - self._tilt)

        return round(self._pan, 2), round(self._tilt, 2)

    def update_no_face(self) -> tuple[float, float]:
        """
        Gently decay toward centre when no face is visible.

        This replaces the hard snap to (0, 0) that caused violent jitter on
        every missed or flickering detection frame.
        """
        self._pan  = self._pan  * (1.0 - self._alpha_nf)
        self._tilt = self._tilt * (1.0 - self._alpha_nf)
        return round(self._pan, 2), round(self._tilt, 2)

    @property
    def current(self) -> tuple[float, float]:
        return round(self._pan, 2), round(self._tilt, 2)


# Module-level singleton used by the FastAPI endpoint.
_tracker = HeadTracker()


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

    Delegates through the module-level HeadTracker singleton so that
    successive calls are smoothed with EMA rather than jumping to raw values.

    Args:
        face:         Detected face bounding box from YuNet.
        frame_width:  Width of the camera frame in pixels.
        frame_height: Height of the camera frame in pixels.
        h_fov_deg:    Camera horizontal field of view in degrees.
        v_fov_deg:    Camera vertical field of view in degrees.
        pan_limit:    Maximum pan angle in either direction (degrees).
        tilt_limit:   Maximum tilt angle in either direction (degrees).

    Returns:
        (pan_deg, tilt_deg) — EMA-smoothed, clamped to ±limit.
        Positive pan  → face is right of centre → turn right.
        Positive tilt → face is above centre   → tilt up.
    """
    return _tracker.update_with_face(
        face,
        frame_width=frame_width,
        frame_height=frame_height,
        h_fov_deg=h_fov_deg,
        v_fov_deg=v_fov_deg,
        pan_limit=pan_limit,
        tilt_limit=tilt_limit,
    )


def no_face_angles() -> tuple[float, float]:
    """
    Return smoothly decayed angles when no face is detected.

    Instead of snapping to (0, 0) this gently drifts the head back toward
    centre so there is no visible jolt when detection flickers.
    """
    return _tracker.update_no_face()
