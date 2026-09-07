#!/usr/bin/env python3
"""beaglebone_experiment/test_spi_display.py — Standalone ST7789 face display test.

Cycles through every face state to verify the SPI panel and wiring work
independently of the rest of the bridge.  Ctrl-C to exit.

Usage: sudo python3 test_spi_display.py [--rotation 0|90|180|270] [--bgr]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Add the repo root to the Python path so we can import beaglebone_experiment
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from beaglebone_experiment.spi_display import SpiDisplay


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ST7789 SPI face display on BBB")
    parser.add_argument("--rotation", type=int, default=0, choices=[0, 90, 180, 270])
    parser.add_argument("--bgr", action="store_true")
    args = parser.parse_args()

    print("Starting ST7789 face display test. Ctrl-C to stop.")

    display = SpiDisplay(rotation=args.rotation, bgr=args.bgr)
    display.start()

    states = ["idle", "listening", "speaking", "thinking", "happy", "sleeping", "focus"]
    idx = 0
    try:
        while True:
            state = states[idx % len(states)]
            print(f"  → {state}")
            display.set_state(state)
            display.show_text(f"Table Tot — {state}", duration=2.0)
            time.sleep(2.0)
            idx += 1
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        display.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
