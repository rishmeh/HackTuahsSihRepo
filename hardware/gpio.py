"""
hardware/gpio.py — GPIO wrappers for Table Tot peripherals.

Uses RPi.GPIO hardware PWM for smooth, jitter-free servo control.

Pin choice
----------
head_pin = 12  (BCM GPIO12, hardware PWM channel 0)
body_pin = 13  (BCM GPIO13, hardware PWM channel 1)

Both are hardware PWM pins on the Raspberry Pi 4/5 that produce a clean
50 Hz signal without CPU involvement, eliminating the jitter that software-
PWM (gpiozero's default backend) causes.

Angle → duty cycle mapping (50 Hz → 20 ms period):
  -45° → 1.0 ms pulse → 5.0 % duty
    0° → 1.5 ms pulse → 7.5 % duty
  +45° → 2.0 ms pulse → 10.0 % duty

Adjust MIN_PULSE_MS / MAX_PULSE_MS in __init__() to calibrate your servos.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIO_AVAILABLE = False
    GPIO = None  # type: ignore


# ---------------------------------------------------------------------------
# PWM servo wrapper
# ---------------------------------------------------------------------------

class _PWMServo:
    """
    Single servo driven by hardware PWM via RPi.GPIO.

    Parameters
    ----------
    pin         BCM pin number (must be a hardware PWM pin: 12, 13, 18, or 19).
    freq_hz     PWM frequency in Hz. Standard hobby servos expect 50 Hz.
    min_pulse_ms  Pulse width (ms) corresponding to min_angle.
    max_pulse_ms  Pulse width (ms) corresponding to max_angle.
    min_angle   Minimum angle in degrees.
    max_angle   Maximum angle in degrees.
    """

    _PERIOD_MS: float  # computed from freq_hz

    def __init__(
        self,
        pin: int,
        freq_hz: float = 50.0,
        min_pulse_ms: float = 1.0,
        max_pulse_ms: float = 2.0,
        min_angle: float = -45.0,
        max_angle: float = 45.0,
    ) -> None:
        self.pin = pin
        self._freq_hz = freq_hz
        self._period_ms = 1000.0 / freq_hz
        self._min_pulse_ms = min_pulse_ms
        self._max_pulse_ms = max_pulse_ms
        self._min_angle = min_angle
        self._max_angle = max_angle

        GPIO.setup(pin, GPIO.OUT)
        self._pwm = GPIO.PWM(pin, freq_hz)
        # Start with the neutral (centre) duty cycle, servo at 0°
        self._pwm.start(self._angle_to_duty(0.0))
        logger.debug("PWM servo on pin %d initialised at 50 Hz", pin)

    def _angle_to_duty(self, angle: float) -> float:
        """Convert an angle in degrees to a PWM duty cycle percentage."""
        angle = max(self._min_angle, min(self._max_angle, angle))
        # Linear interpolation: angle → pulse width in ms
        ratio = (angle - self._min_angle) / (self._max_angle - self._min_angle)
        pulse_ms = self._min_pulse_ms + ratio * (self._max_pulse_ms - self._min_pulse_ms)
        return (pulse_ms / self._period_ms) * 100.0

    def set_angle(self, angle: float) -> None:
        """Move the servo to *angle* degrees."""
        self._pwm.ChangeDutyCycle(self._angle_to_duty(angle))

    def detach(self) -> None:
        """Stop the PWM signal (servo holds last position then relaxes)."""
        self._pwm.stop()
        GPIO.cleanup(self.pin)


# ---------------------------------------------------------------------------
# Dual-servo controller (head pan + body tilt)
# ---------------------------------------------------------------------------

class ServoController:
    """
    Dual servo controller for head and body movement using hardware PWM.

    Both servos run at 50 Hz. The PWM signal is generated entirely in
    hardware on the Pi's dedicated PWM timer so there is no CPU-induced
    jitter (unlike gpiozero's software-PWM backend).

    Smooth movement
    ---------------
    track() uses a small software interpolation loop (STEPS × step_ms)
    so the servo glides to the target instead of jumping, which is the
    second major cause of visible jitter in addition to sensor noise.

    Ambient animation
    -----------------
    start_ambient() launches a looping background thread that gently sways
    the head when no face is present, making the robot feel alive to kids.
    Call stop_ambient() (or any named gesture / track()) to cancel it.
    """

    # Soft-step parameters for track(): tune these to taste.
    # TRACK_STEPS × TRACK_STEP_MS sets total slew time per frame.
    # e.g. 6 steps × 20 ms = 120 ms max slew — invisible lag at ~7 fps.
    TRACK_STEPS: int = 6
    TRACK_STEP_MS: float = 20.0  # ms between steps

    def __init__(
        self,
        head_pin: int = 12,
        body_pin: int = 13,
        min_angle: float = -45.0,
        max_angle: float = 45.0,
        min_pulse_ms: float = 1.0,
        max_pulse_ms: float = 2.0,
        freq_hz: float = 50.0,
    ) -> None:
        if not GPIO_AVAILABLE:
            raise RuntimeError(
                "RPi.GPIO is not available. "
                "Install with: pip install RPi.GPIO"
            )

        self._lock = threading.Lock()
        self._min_angle = min_angle
        self._max_angle = max_angle
        self._gesture_generation = 0
        self._gesture_thread: Optional[threading.Thread] = None
        self._closed = False
        self._head_angle = 0.0
        self._body_angle = 0.0

        # Ambient idle state
        self._ambient_active = False
        self._ambient_thread: Optional[threading.Thread] = None

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        self.head = _PWMServo(
            head_pin,
            freq_hz=freq_hz,
            min_pulse_ms=min_pulse_ms,
            max_pulse_ms=max_pulse_ms,
            min_angle=min_angle,
            max_angle=max_angle,
        )
        self.body = _PWMServo(
            body_pin,
            freq_hz=freq_hz,
            min_pulse_ms=min_pulse_ms,
            max_pulse_ms=max_pulse_ms,
            min_angle=min_angle,
            max_angle=max_angle,
        )
        logger.info(
            "ServoController using hardware PWM | pins=%d/%d | %.0f Hz | "
            "pulse=%.1f–%.1f ms | angles=%.0f–%.0f°",
            head_pin, body_pin, freq_hz,
            min_pulse_ms, max_pulse_ms,
            min_angle, max_angle,
        )

    def _set_head(self, angle: float) -> None:
        with self._lock:
            if self._closed:
                return
            self._head_angle = max(self._min_angle, min(self._max_angle, angle))
            self.head.set_angle(self._head_angle)

    def _set_body(self, angle: float) -> None:
        with self._lock:
            if self._closed:
                return
            self._body_angle = max(self._min_angle, min(self._max_angle, angle))
            self.body.set_angle(self._body_angle)

    # ------------------------------------------------------------------
    # Internal: run a pose sequence asynchronously
    # ------------------------------------------------------------------

    def _gesture(self, poses: list[tuple[float, float, float]]) -> None:
        """
        Run a replaceable, non-blocking list of head/body poses.

        Each pose is (head_angle, body_angle, hold_seconds).
        The servo steps smoothly between consecutive poses using
        linear interpolation so motion never looks like a hard snap.
        """
        self._stop_ambient()
        with self._lock:
            self._gesture_generation += 1
            generation = self._gesture_generation

        def run() -> None:
            # Start from the current actual position so the first move
            # is also smooth, not a jump.
            with self._lock:
                from_head = self._head_angle
                from_body = self._body_angle

            for (to_head, to_body, hold) in poses:
                steps = max(1, int(hold / (self.TRACK_STEP_MS / 1000.0)))
                for step in range(1, steps + 1):
                    with self._lock:
                        if self._closed or generation != self._gesture_generation:
                            return
                    t = step / steps
                    # Smooth ease-in-out via cosine
                    ease = (1.0 - math.cos(t * math.pi)) / 2.0
                    interp_head = from_head + (to_head - from_head) * ease
                    interp_body = from_body + (to_body - from_body) * ease
                    self._set_head(interp_head)
                    self._set_body(interp_body)
                    time.sleep(self.TRACK_STEP_MS / 1000.0)
                from_head = to_head
                from_body = to_body

        thread = threading.Thread(target=run, daemon=True, name="tabletot-servo-gesture")
        self._gesture_thread = thread
        thread.start()

    # ------------------------------------------------------------------
    # Ambient idle animation (runs when face is absent for a while)
    # ------------------------------------------------------------------

    def _stop_ambient(self) -> None:
        """Cancel the ambient loop if it is running."""
        self._ambient_active = False
        # The ambient thread checks _ambient_active; it will exit on its own.

    def start_ambient(self) -> None:
        """
        Start a looping, gentle idle sway animation so the robot looks
        alive when nobody is in front of it.

        The animation is a slow sinusoidal sweep of the head combined with
        occasional random-ish body tilts, giving the impression of a curious
        little creature looking around.
        """
        if self._ambient_active:
            return  # Already running
        self._stop_gesture()
        self._ambient_active = True

        def _ambient_loop() -> None:
            phase = 0.0
            body_phase = math.pi / 3  # body slightly offset from head
            while self._ambient_active and not self._closed:
                # Slow head sweep: ±12° over ~4 s cycle
                head_angle = 12.0 * math.sin(phase)
                # Body tilts gently at half amplitude: ±5° over ~6 s cycle
                body_angle = 5.0 * math.sin(body_phase * 0.7)
                self._set_head(head_angle)
                self._set_body(body_angle)
                phase += 0.05          # step ~0.8°/frame at 50 ms tick
                body_phase += 0.035
                time.sleep(0.05)

        thread = threading.Thread(target=_ambient_loop, daemon=True, name="tabletot-servo-ambient")
        self._ambient_thread = thread
        thread.start()
        logger.debug("Ambient idle animation started")

    def stop_ambient(self) -> None:
        """Stop the ambient animation (call before gestures / tracking)."""
        self._stop_ambient()

    def _stop_gesture(self) -> None:
        """Bump gesture generation so any running gesture thread exits."""
        with self._lock:
            self._gesture_generation += 1

    # ------------------------------------------------------------------
    # Named gestures — each cancels ambient + previous gesture
    # ------------------------------------------------------------------

    def idle(self) -> None:
        """Return smoothly to centre."""
        self._gesture([(0.0, 0.0, 0.4)])

    def listen(self) -> None:
        """
        Lean head slightly toward the speaker and bob once — shows attentiveness.
        Kids interpret a head-tilt as 'the robot is listening carefully'.
        """
        self._gesture([
            (12.0,  3.0, 0.30),   # tilt toward speaker
            (10.0,  5.0, 0.25),   # small nod down
            (14.0,  2.0, 0.25),   # nod up
            (12.0,  3.0, 0.60),   # hold attentive pose
        ])

    def speak(self) -> None:
        """
        Rhythmic head bobs while speaking — matches natural speech cadence.
        Body sways opposite to head to look energetic and friendly.
        """
        self._gesture([
            ( 8.0, -4.0, 0.20),
            (-4.0,  5.0, 0.18),
            (10.0, -5.0, 0.20),
            (-3.0,  4.0, 0.18),
            ( 6.0, -3.0, 0.20),
            ( 0.0,  0.0, 0.15),
        ])

    def happy(self) -> None:
        """
        An enthusiastic nod and body sway when recognition succeeds.
        Clearly visible and satisfying for kids.
        """
        self._gesture([
            ( 20.0, -18.0, 0.18),
            (-10.0,  18.0, 0.18),
            ( 22.0, -15.0, 0.18),
            (-8.0,   15.0, 0.18),
            ( 15.0,  -8.0, 0.18),
            (  0.0,   0.0, 0.20),
        ])

    def thinking(self) -> None:
        """
        Slow head tilt to one side + gentle body lean — the classic 'hmm'
        pose.  Runs as a repeating sequence so it feels like the robot is
        genuinely mulling things over.
        """
        self._gesture([
            (-18.0,  6.0, 0.50),   # tilt left, lean
            (-20.0,  8.0, 0.40),   # settle deeper
            (-16.0,  5.0, 0.40),   # small shift
            (-18.0,  7.0, 0.60),   # hold
        ])

    def focus(self) -> None:
        """
        Square-on, slightly forward lean — robot is concentrating.
        """
        self._gesture([
            ( 0.0, -8.0, 0.35),   # lean forward (body forward = negative tilt here)
            ( 2.0, -9.0, 0.30),   # tiny tilt right
            (-1.0, -8.0, 0.30),   # micro correction
            ( 0.0, -8.0, 0.40),   # hold
        ])

    # ------------------------------------------------------------------
    # Continuous face tracking (fast path — no gesture thread)
    # ------------------------------------------------------------------

    def track(self, pan: float, tilt: float) -> None:
        """
        Move smoothly toward (pan, tilt) angles for continuous face tracking.

        Unlike the named gestures this stays on the calling thread but
        interleaves short PWM steps so motion is visually smooth rather
        than an instant jump.  Also cancels any running gesture / ambient.

        Args:
            pan:  Horizontal angle in degrees.  Positive = right of centre.
            tilt: Vertical angle in degrees.    Positive = above centre.
        """
        # Cancel ambient and bump gesture generation so any running gesture exits.
        self._stop_ambient()
        with self._lock:
            self._gesture_generation += 1
            from_head = self._head_angle
            from_body = self._body_angle

        pan  = max(self._min_angle, min(self._max_angle, pan))
        tilt = max(self._min_angle, min(self._max_angle, tilt))

        for step in range(1, self.TRACK_STEPS + 1):
            t = step / self.TRACK_STEPS
            ease = (1.0 - math.cos(t * math.pi)) / 2.0
            self._set_head(from_head + (pan  - from_head) * ease)
            self._set_body(from_body + (tilt - from_body) * ease)
            time.sleep(self.TRACK_STEP_MS / 1000.0)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        self._stop_ambient()
        with self._lock:
            self._closed = True
            self._gesture_generation += 1
        if self._gesture_thread and self._gesture_thread.is_alive():
            self._gesture_thread.join(timeout=1.0)
        with self._lock:
            try:
                self.head.detach()
                self.body.detach()
            except Exception as exc:
                logger.warning("Error during servo cleanup: %s", exc)

    @property
    def head_angle(self) -> float:
        with self._lock:
            return self._head_angle

    @property
    def body_angle(self) -> float:
        with self._lock:
            return self._body_angle
