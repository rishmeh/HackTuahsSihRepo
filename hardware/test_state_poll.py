#!/usr/bin/env python3
"""
Standalone state polling test — polls the laptop for the servo state and shows
what the Pi should do.

Usage (on Pi):
    LAPTOP_URL=http://192.168.1.100:8000 python3 hardware/test_state_poll.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LAPTOP_URL = os.getenv("LAPTOP_URL", "http://localhost:8000")


def main():
    try:
        import httpx
    except ImportError:
        print("This test requires httpx on the Pi.")
        sys.exit(1)

    print(f"State polling test → polling {LAPTOP_URL}/hardware/state")
    print("Press Ctrl+C to stop.\n")

    client = httpx.Client(timeout=5.0)

    try:
        while True:
            resp = client.get(f"{LAPTOP_URL}/hardware/state")
            if resp.status_code == 200:
                state = resp.json()
                print(
                    f"  servo_state: {state.get('servo_state', 'idle')} | "
                    f"revision: {state.get('revision', 0)}"
                )
            else:
                print(f"  ERROR: {resp.status_code} - {resp.text}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nState polling test complete.")


if __name__ == "__main__":
    main()
