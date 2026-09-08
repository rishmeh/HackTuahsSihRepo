#!/usr/bin/env python3
"""Cycle every Table Tot face on a wired ST7789V GMT020-02-8P display.

No laptop, camera, or servo is needed. Stop with Ctrl-C.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.st7789v_display import ST7789VDisplay

SEQUENCE = ["idle", "listening", "thinking", "speaking", "happy", "focus", "sleeping"]


def main() -> None:
    display = ST7789VDisplay()
    display.start()
    print("Cycling faces: " + " -> ".join(SEQUENCE))
    try:
        while True:
            for state in SEQUENCE:
                print(f"  {state}")
                display.set_state(state)
                if state == "speaking":
                    display.show_text("Hello! I am Table Tot", duration=2.5)
                elif state == "happy":
                    display.show_text("Face recognized!", duration=2.5)
                elif state == "thinking":
                    display.show_text("Let me think...", duration=2.5)
                time.sleep(3)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        display.stop()


if __name__ == "__main__":
    main()
