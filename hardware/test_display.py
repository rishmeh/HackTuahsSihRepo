#!/usr/bin/env python3
"""
Standalone test for the Pi-connected face display.

Supports both:
  - ST7789V SPI TFT display (wired via SPI0 / GPIO)
  - HDMI IPS display (via pygame)

Usage:
    python3 hardware/test_display.py                # Defaults to st7789v (or DISPLAY_DRIVER env)
    python3 hardware/test_display.py --driver st7789v
    python3 hardware/test_display.py --driver hdmi
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATES = ["idle", "listening", "thinking", "speaking", "happy", "focus", "sleeping"]


def test_st7789v():
    print("\n" + "=" * 55)
    print("  Testing ST7789V SPI Display (240x320)")
    print("=" * 55)

    try:
        from hardware.st7789v_display import ST7789VDisplay
    except ImportError as e:
        print(f"\n[ERROR] Missing dependency: {e}")
        print("Please ensure spidev, Pillow, and lgpio are installed:")
        print("  sudo apt install -y python3-spidev python3-pil python3-lgpio")
        sys.exit(1)

    print("[1/3] Initializing GPIO & SPI0 interface...")
    try:
        display = ST7789VDisplay(fps=10)
    except Exception as exc:
        print(f"\n[FAILED] Could not initialize ST7789V: {exc}")
        print("\nTroubleshooting checklist:")
        print("1. Is SPI enabled? Run: sudo raspi-config nonint do_spi 0")
        print("2. Check wiring:")
        print("   - Pin 17 (3.3V) -> VCC")
        print("   - Pin 20 (GND)  -> GND")
        print("   - Pin 23 (GPIO11 SCLK) -> SCL")
        print("   - Pin 19 (GPIO10 MOSI) -> SDA")
        print("   - Pin 18 (GPIO24)      -> RST")
        print("   - Pin 22 (GPIO25)      -> DC")
        print("   - Pin 24 (GPIO8 CE0)   -> CS")
        print("   - Pin 21 (GPIO9)       -> BL (Backlight)")
        print("3. If backlight is dark, try connecting BL directly to 3.3V (Pin 1 or 17).")
        sys.exit(1)

    print("      ✓ Backlight ON, SPI0 CE0 opened successfully.\n")

    print("[2/3] Diagnostics: Screen Color Flash Test (1s each)...")
    colors = [
        ("RED", (255, 0, 0)),
        ("GREEN", (0, 255, 0)),
        ("BLUE", (0, 0, 255)),
        ("CYAN", (0, 255, 255)),
        ("BLACK", (0, 0, 0)),
    ]
    for name, rgb in colors:
        print(f"      Filling: {name}...")
        display.fill(rgb)
        time.sleep(1.0)

    print("\n[3/3] Starting Animated Face Cycling...")
    print("      States: " + " -> ".join(STATES))
    print("      Press Ctrl+C to stop.\n")

    display.start()
    try:
        while True:
            for state in STATES:
                print(f"  → Face state: {state}")
                display.set_state(state)
                time.sleep(3.0)
    except KeyboardInterrupt:
        print("\nTest stopped by user.")
    finally:
        display.stop()
        print("Display turned off cleanly.")


def test_hdmi(fullscreen: bool):
    print("\n" + "=" * 55)
    print("  Testing HDMI Display (Pygame)")
    print("=" * 55)

    from hardware.display import Display
    display = Display(width=800, height=480, fullscreen=fullscreen)
    display.start()

    print("Display test — cycling through face states.")
    print("Close the window or press Ctrl+C to stop.\n")

    try:
        while True:
            for state in STATES:
                print(f"  → {state}")
                display.set_state(state)
                if state == "speaking":
                    display.show_text("Hello! I'm Table Tot", duration=2.0)
                elif state == "happy":
                    display.show_text("Yay! That's great!", duration=2.0)
                elif state == "thinking":
                    display.show_text("Hmm, let me think...", duration=2.0)
                time.sleep(3.0)
    except KeyboardInterrupt:
        print("\nTest stopped.")
    finally:
        display.stop()


def main():
    parser = argparse.ArgumentParser(description="Table Tot Face Display Tester")
    default_driver = os.getenv("DISPLAY_DRIVER", "st7789v").lower()
    parser.add_argument(
        "--driver",
        choices=["st7789v", "hdmi"],
        default=default_driver,
        help="Display driver to test (default: st7789v)",
    )
    parser.add_argument("--fullscreen", action="store_true", help="Fullscreen mode (HDMI only)")
    args = parser.parse_args()

    if args.driver == "st7789v":
        test_st7789v()
    else:
        test_hdmi(args.fullscreen)


if __name__ == "__main__":
    main()
