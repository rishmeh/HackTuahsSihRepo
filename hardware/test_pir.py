#!/usr/bin/env python3
"""
Legacy PIR test. The current build has no PIR sensor.
Requires a PIR sensor connected to GPIO 17.
Usage:
    python3 hardware/test_pir.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from gpiozero import MotionSensor
except ImportError:
    print("ERROR: gpiozero not installed. Run: pip install gpiozero")
    sys.exit(1)


def main():
    print("Testing PIR sensor on GPIO 17...")
    print("Press Ctrl+C to stop.\n")

    pir = MotionSensor(17)
    motion_count = 0

    print("Waiting for motion...")

    try:
        while True:
            pir.wait_for_motion()
            motion_count += 1
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] MOTION detected! (count: {motion_count})")

            pir.wait_for_no_motion()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] No motion")
    except KeyboardInterrupt:
        print(f"\nPIR test complete. Detected {motion_count} motion event(s).")
        sys.exit(0)


if __name__ == "__main__":
    main()
