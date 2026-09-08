#!/usr/bin/env python3
"""Compatibility test entry retained from the supplied working ``file.py``.

The SPI setup is now shared with the robot display driver, so this test uses
the exact same code path that the laptop-controlled robot will use.
"""

from hardware.test_st7789v_faces import main


if __name__ == "__main__":
    main()
