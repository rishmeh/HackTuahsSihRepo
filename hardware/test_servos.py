#!/usr/bin/env python3
"""
Standalone servo test.
Moves each servo through its range.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.gpio import ServoController


def main():
    try:
        servos = ServoController(head_pin=12, body_pin=13)
        print("Using real GPIO")
    except Exception as exc:
        print(f"Cannot use real GPIO ({exc}). Install gpiozero and run on Pi.")
        sys.exit(1)

    states = [
        ("idle", lambda: servos.idle()),
        ("listen", lambda: servos.listen()),
        ("speak", lambda: servos.speak()),
        ("happy", lambda: servos.happy()),
        ("thinking", lambda: servos.thinking()),
        ("focus", lambda: servos.focus()),
    ]

    for name, action in states:
        print(f"Testing {name}...")
        action()
        time.sleep(1.5)

    print("Returning to idle...")
    servos.idle()
    time.sleep(1)

    servos.cleanup()
    print("Servo test complete!")


if __name__ == "__main__":
    main()
