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
    """

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

    def _gesture(self, poses: list[tuple[float, float, float]]) -> None:
        """Run a replaceable, non-blocking list of head/body poses."""
        with self._lock:
            self._gesture_generation += 1
            generation = self._gesture_generation

        def run() -> None:
            for head, body, duration in poses:
                with self._lock:
                    if self._closed or generation != self._gesture_generation:
                        return
                self._set_head(head)
                self._set_body(body)
                time.sleep(duration)

        thread = threading.Thread(target=run, daemon=True, name="tabletot-servo-gesture")
        self._gesture_thread = thread
        thread.start()

    def idle(self):
        self._gesture([(0.0, 0.0, 0.1)])

    def listen(self):
        self._gesture([(15.0, 0.0, 0.1)])

    def speak(self):
        self._gesture([(8.0, -4.0, 0.18), (-2.0, 4.0, 0.18), (8.0, -4.0, 0.18)])

    def happy(self):
        # A short nod and body sway is clearly visible when recognition succeeds.
        self._gesture([
            (18.0, -15.0, 0.20),
            (-5.0,  15.0, 0.20),
            (18.0, -12.0, 0.20),
            (0.0,    0.0, 0.10),
        ])

    def thinking(self):
        self._gesture([(-15.0, 7.0, 0.1)])

    def focus(self):
        self._gesture([(0.0, -5.0, 0.1)])

    def track(self, pan: float, tilt: float) -> None:
        """
        Move directly to (pan, tilt) angles for continuous face tracking.

        Unlike the named gestures this is NOT asynchronous and does NOT start
        a gesture thread — it applies the angles immediately and returns.
        This keeps the servo latency as low as possible during live tracking.

        Args:
            pan:  Horizontal angle in degrees.  Positive = right of centre.
            tilt: Vertical angle in degrees.    Positive = above centre.
        """
        # Bump the gesture generation so any running gesture thread aborts.
        with self._lock:
            self._gesture_generation += 1
        self._set_head(pan)
        self._set_body(tilt)

    def cleanup(self) -> None:
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
