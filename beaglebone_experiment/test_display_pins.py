#!/usr/bin/env python3
"""Pin-by-pin diagnostic for ST7789 display.
Tests each GPIO and SPI line individually so you can verify with a multimeter or LED."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gpiod
import spidev

def gpio_init(gpio_num, consumer="test"):
    bank = gpio_num // 32
    line = gpio_num % 32
    chip_name = f"gpiochip{bank}"
    if not os.path.exists(f"/dev/{chip_name}"):
        for i in range(4):
            if os.path.exists(f"/dev/gpiochip{i}"):
                chip_name = f"gpiochip{i}"
                break
    chip = gpiod.Chip(chip_name)
    line_obj = chip.get_line(line)
    line_obj.request(consumer=consumer, type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
    return line_obj, chip

def gpio_set(line_obj, val):
    line_obj.set_value(val)

print("=== ST7789 Pin-by-Pin Diagnostic ===\n")
print("Use a multimeter or LED to verify each pin toggles.")
print("Each pin will blink 5 times (0.5s ON, 0.5s OFF).\n")

# Test each GPIO pin
pins = [
    (48, "DC/RS", "P9_15"),
    (31, "RST", "P9_13"),
    (50, "BL", "P9_14"),
]

for gpio, name, pin in pins:
    print(f"Testing {name} (GPIO {gpio}, {pin})...")
    try:
        line, chip = gpio_init(gpio, f"test_{name}")
        for i in range(5):
            gpio_set(line, 1)
            time.sleep(0.5)
            gpio_set(line, 0)
            time.sleep(0.5)
        line.release()
        chip.close()
        print(f"  Done. Did you see {name} toggle?\n")
    except Exception as e:
        print(f"  FAIL: {e}\n")

# Test SPI pins
print("Testing SPI0 (P9_17 CS, P9_18 MOSI, P9_22 SCK)...")
print("  Opening SPI device...")
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1_000_000  # 1 MHz for easier measurement
    spi.mode = 0b00
    
    print("  Sending 100 bytes of 0xFF (MOSI should go high, SCK should toggle)...")
    for i in range(10):
        spi.writebytes([0xFF] * 10)
        time.sleep(0.1)
    
    spi.close()
    print("  Done. Did you see SCK and MOSI activity?\n")
except Exception as e:
    print(f"  FAIL: {e}\n")

# Test alternative DC pins
print("=== Alternative DC Pin Test ===")
print("If DC (P9_15) doesn't work, trying other pins...\n")

alt_dc_pins = [
    (30, "P9_11", "UART4_RXD"),
    (49, "P9_23", "GPMC_A3"),
    (15, "P9_24", "UART4_TXD"),
    (14, "P9_26", "UART4_RTS"),
    (115, "P9_27", "MCASP0_FSR"),
]

for gpio, pin, func in alt_dc_pins:
    print(f"  Testing DC on {pin} (GPIO {gpio}, {func})...")
    try:
        line, chip = gpio_init(gpio, f"test_dc_{gpio}")
        for i in range(3):
            gpio_set(line, 1)
            time.sleep(0.3)
            gpio_set(line, 0)
            time.sleep(0.3)
        line.release()
        chip.close()
        print(f"    Toggled. If display works with this, use it for DC.\n")
    except Exception as e:
        print(f"    FAIL: {e}\n")

print("=== Summary ===")
print("If NO pins toggle:")
print("  - Check wiring (loose connections)")
print("  - Check if gpiod has permission (run as root)")
print("")
print("If GPIO toggles but display stays black:")
print("  - SPI may not be sending data (check SCK/MOSI)")
print("  - Panel may not be ST7789 (could be ILI9341, ST7735, etc.)")
print("  - Panel may be dead")
print("")
print("If you found an alternative DC pin that works:")
print("  - Update DISPLAY_DC_GPIO in .env.bbb")
print("  - Update spi_display.py DEFAULT_DC_GPIO")
