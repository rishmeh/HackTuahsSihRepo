"""
hardware/gpio.py — GPIO wrappers for Table Tot peripherals.

Uses gpiozero for clean, testable hardware abstractions.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from gpiozero import Servo, AngularServo
    GPIO_AVAILABLE = True
except (ImportError, OSError):
    GPIO_AVAILABLE = False
    Servo = None
    AngularServo = None


class ServoController:
    """
    Dual servo controller for head and body movement.
    """

    def __init__(
        self,
        head_pin: int = 12,
        body_pin: int = 13,
        min_angle: float = -45.0,
        max_angle: float = 45.0,
        min_pulse_width: float = 0.0005,
        max_pulse_width: float = 0.0025,
    ):
        if not GPIO_AVAILABLE:
            raise RuntimeError(
                "gpiozero is not available. "
                "Install with: pip install gpiozero"
            )

        self._lock = threading.Lock()
        self._head_pin = head_pin
        self._body_pin = body_pin
        self._min_angle = min_angle
        self._max_angle = max_angle
        self._gesture_generation = 0
        self._gesture_thread: Optional[threading.Thread] = None
        self._closed = False

        try:
            self.head = AngularServo(
                head_pin,
                min_angle=min_angle,
                max_angle=max_angle,
                min_pulse_width=min_pulse_width,
                max_pulse_width=max_pulse_width,
            )
            self.body = AngularServo(
                body_pin,
                min_angle=min_angle,
                max_angle=max_angle,
                min_pulse_width=min_pulse_width,
                max_pulse_width=max_pulse_width,
            )
            self._angular = True
            logger.info("ServoController using AngularServo")
        except Exception:
            self.head = Servo(head_pin)
            self.body = Servo(body_pin)
            self._angular = False
            logger.info("ServoController using Servo (fallback)")

        self._head_angle = 0.0
        self._body_angle = 0.0

    def _set_head(self, angle: float):
        with self._lock:
            if self._closed:
                return
            self._head_angle = max(self._min_angle, min(self._max_angle, angle))
            if self._angular:
                self.head.angle = self._head_angle
            else:
                self.head.value = self._head_angle / self._max_angle

    def _set_body(self, angle: float):
        with self._lock:
            if self._closed:
                return
            self._body_angle = max(self._min_angle, min(self._max_angle, angle))
            if self._angular:
                self.body.angle = self._body_angle
            else:
                self.body.value = self._body_angle / self._max_angle

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
            (-5.0, 15.0, 0.20),
            (18.0, -12.0, 0.20),
            (0.0, 0.0, 0.10),
        ])

    def thinking(self):
        self._gesture([(-15.0, 7.0, 0.1)])

    def focus(self):
        self._gesture([(0.0, -5.0, 0.1)])

    def cleanup(self):
        with self._lock:
            self._closed = True
            self._gesture_generation += 1
        if self._gesture_thread and self._gesture_thread.is_alive():
            self._gesture_thread.join(timeout=1.0)
        with self._lock:
            try:
                if self._angular:
                    self.head.detach()
                    self.body.detach()
                else:
                    self.head.close()
                    self.body.close()
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
