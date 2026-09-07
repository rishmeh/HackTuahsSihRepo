"""Manual, deliberate PRU servo tests. Run only after loading firmware."""

from __future__ import annotations

import argparse
import time

from pru_servo import PruServoController


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--neutral", action="store_true")
    group.add_argument("--head-left", action="store_true")
    group.add_argument("--head-right", action="store_true")
    group.add_argument("--body-left", action="store_true")
    group.add_argument("--body-right", action="store_true")
    args = parser.parse_args()
    controller = PruServoController()
    try:
        if args.head_left:
            controller.set_angles(-30, 0)
        elif args.head_right:
            controller.set_angles(30, 0)
        elif args.body_left:
            controller.set_angles(0, -30)
        elif args.body_right:
            controller.set_angles(0, 30)
        else:
            controller.set_angles(0, 0)
        time.sleep(2)
    finally:
        controller.cleanup()


if __name__ == "__main__":
    main()
