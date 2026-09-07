"""Host-side pulse writer for the BBB PRU0 servo firmware.

The firmware owns PWM timing.  This module only writes two 32-bit microsecond
values into AM335x PRU shared RAM, so it must run as root.
"""

from __future__ import annotations

import mmap
import os
import struct
import threading

PRU_SHARED_RAM_PHYS = 0x4A310000
MAP_LENGTH = 4096
MAGIC = 0x544F5431  # "TOT1"
NEUTRAL_US = 1500
MIN_US = 500
MAX_US = 2500


class PruServoController:
    """Two channels: head=P9_31/PRU0 R30 bit 0; body=P9_29/bit 1."""

    def __init__(
        self,
        head_min_us: int = 1000,
        head_max_us: int = 2000,
        body_min_us: int = 1000,
        body_max_us: int = 2000,
    ) -> None:
        if os.geteuid() != 0:
            raise RuntimeError("PRU shared RAM needs root; start with sudo")
        self._fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self._memory = mmap.mmap(
            self._fd,
            MAP_LENGTH,
            flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE,
            offset=PRU_SHARED_RAM_PHYS,
        )
        self._lock = threading.Lock()
        self._closed = False
        self.head_min_us = self._validate_limit(head_min_us)
        self.head_max_us = self._validate_limit(head_max_us)
        self.body_min_us = self._validate_limit(body_min_us)
        self.body_max_us = self._validate_limit(body_max_us)
        if self.head_min_us >= self.head_max_us or self.body_min_us >= self.body_max_us:
            raise ValueError("each servo minimum must be below its maximum")
        self.set_pulses(NEUTRAL_US, NEUTRAL_US)

    @staticmethod
    def _validate_limit(value: int) -> int:
        value = int(value)
        if not MIN_US <= value <= MAX_US:
            raise ValueError(f"servo pulse must be {MIN_US}..{MAX_US} us")
        return value

    @staticmethod
    def _angle_to_pulse(angle: float, low: int, high: int) -> int:
        angle = max(-45.0, min(45.0, float(angle)))
        return round(low + ((angle + 45.0) / 90.0) * (high - low))

    def set_pulses(self, head_us: int, body_us: int) -> None:
        """Publish a complete two-servo target for the next PRU frame."""
        head_us = self._validate_limit(head_us)
        body_us = self._validate_limit(body_us)
        with self._lock:
            if self._closed:
                return
            # Invalidate first, then publish both channels and the ready magic.
            # Each individual 32-bit aligned write is atomic on this AM335x path.
            struct.pack_into("<I", self._memory, 0, 0)
            struct.pack_into("<II", self._memory, 4, head_us, body_us)
            struct.pack_into("<I", self._memory, 0, MAGIC)
            self._memory.flush()

    def set_angles(self, head_angle: float, body_angle: float) -> None:
        self.set_pulses(
            self._angle_to_pulse(head_angle, self.head_min_us, self.head_max_us),
            self._angle_to_pulse(body_angle, self.body_min_us, self.body_max_us),
        )

    def cleanup(self) -> None:
        self.set_pulses(NEUTRAL_US, NEUTRAL_US)
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._memory.close()
            os.close(self._fd)
