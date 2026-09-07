#!/usr/bin/env python3
"""
Standalone test for the Pi-connected IPS face display.

Usage:
    python3 hardware/test_display.py
    python3 hardware/test_display.py --fullscreen
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.display import Display

STATES = ["idle", "listening", "speaking", "happy", "thinking", "focus", "sleeping"]


def main():
    fullscreen = "--fullscreen" in sys.argv
    display = Display(width=800, height=480, fullscreen=fullscreen)
    display.start()

    print("Display test — cycling through face states.")
    print("Close the window or press Ctrl+C to stop.\n")

    print("States: idle → listening → speaking → happy → focus → sleeping → idle")
    for state in STATES * 3:  # cycle 3 times
        print(f"  → {state}")
        display.set_state(state)

        if state == "speaking":
            display.show_text("Hello! I'm Table Tot", duration=2.0)
        elif state == "happy":
            display.show_text("Yay! That's great!", duration=2.0)
        elif state == "thinking":
            display.show_text("Hmm, let me think...", duration=2.0)

        time.sleep(3.0)

    print("\nDisplay test complete.")
    display.stop()


if __name__ == "__main__":
    main()
