#!/usr/bin/env python3
"""Quick test script for ST7789 display with offset/MADCTL variations."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from beaglebone_experiment.spi_display import SpiDisplay

configs = [
    {"col_offset": 80, "row_offset": 80, "label": "offset 80,80 (most common)"},
    {"col_offset": 0, "row_offset": 80, "label": "offset 0,80"},
    {"col_offset": 80, "row_offset": 0, "label": "offset 80,0"},
    {"rotation": 90, "label": "rotation=90"},
    {"rotation": 180, "col_offset": 80, "row_offset": 80, "label": "rotation=180 offset 80,80"},
    {"rotation": 270, "col_offset": 80, "row_offset": 80, "label": "rotation=270 offset 80,80"},
    {"bgr": True, "col_offset": 80, "row_offset": 80, "label": "BGR offset 80,80"},
    {"bgr": True, "label": "BGR no offset"},
]

print("Testing ST7789 display configurations.")
print("Look for a visible face on the panel for each test.")
print("Ctrl-C to skip to next test.\n")

for i, cfg in enumerate(configs):
    label = cfg.pop("label")
    print(f"Test {i+1}: {label}")
    print(f"  Config: {cfg}")
    try:
        d = SpiDisplay(**cfg)
        d.start()
        time.sleep(1)
        d.set_state("happy")
        print("  → Showing happy face for 5 seconds...")
        time.sleep(5)
        d.stop()
        print("  Done.\n")
    except KeyboardInterrupt:
        print("  Skipped.\n")
        try:
            d.stop()
        except Exception:
            pass
    except Exception as exc:
        print(f"  Error: {exc}\n")

print("All tests complete. Which one showed a face?")
