#!/usr/bin/env python3
"""Comprehensive ST7789V display test — multiple wiring/config combinations."""
import spidev
import gpiod
import time
import sys

def gpio_init(n):
    bank, line = n // 32, n % 32
    chip = gpiod.Chip(f"gpiochip{bank}")
    l = chip.get_line(line)
    l.request(consumer="test", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
    return l, chip

dc, _ = gpio_init(48)
rst, _ = gpio_init(31)
bl, _ = gpio_init(50)

print("=== ST7789V Comprehensive Test ===\n")

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0

# Reset
rst.set_value(1); time.sleep(0.01)
rst.set_value(0); time.sleep(0.01)
rst.set_value(1); time.sleep(0.15)

bl.set_value(1)

def cmd(c):
    dc.set_value(0); spi.writebytes([c])
def data(d):
    dc.set_value(1); spi.writebytes(list(d) if isinstance(d, (bytes, bytearray)) else [d])

def fill_color(high, low, label):
    cmd(0x2A); data(bytes([0x00, 0x00, 0x00, 0xEF]))
    cmd(0x2B); data(bytes([0x00, 0x00, 0x00, 0xEF]))
    cmd(0x2C)
    dc.set_value(1)
    for row in range(240):
        for col in range(240):
            spi.writebytes([high, low])
        if row % 40 == 0:
            print(f"  {label} row {row}/240...")
    time.sleep(2)

def init_st7789v():
    cmd(0x01); time.sleep(0.15)
    cmd(0x11); time.sleep(0.12)
    cmd(0x36); data(0x00)
    cmd(0x3A); data(0x55)
    cmd(0xB2); data(bytes([0x0C, 0x0C, 0x00, 0x33, 0x33]))
    cmd(0xB7); data(0x35)
    cmd(0xBB); data(0x19)
    cmd(0xC0); data(0x2C)
    cmd(0xC2); data(0x01)
    cmd(0xC3); data(0x12)
    cmd(0xC4); data(0x20)
    cmd(0xC6); data(0x0F)
    cmd(0xD0); data(bytes([0xA4, 0xA1]))
    cmd(0xE0); data(bytes([0xD0, 0x04, 0x0D, 0x11, 0x13, 0x2B, 0x3F, 0x54, 0x4C, 0x18, 0x0D, 0x0B, 0x1F, 0x23]))
    cmd(0xE1); data(bytes([0xD0, 0x04, 0x0C, 0x11, 0x13, 0x2C, 0x3F, 0x44, 0x51, 0x2F, 0x1F, 0x1F, 0x20, 0x23]))
    cmd(0x21); time.sleep(0.01)
    cmd(0x13); time.sleep(0.01)
    cmd(0x29); time.sleep(0.12)

# Test 1: Normal
print("Test 1: Normal init, fill RED...")
init_st7789v()
fill_color(0xF8, 0x00, "RED")
print("  Did you see RED?\n")

# Test 2: With column offset
print("Test 2: With column offset 40, row offset 0...")
spi.close()
time.sleep(0.5)
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0
rst.set_value(0); time.sleep(0.01); rst.set_value(1); time.sleep(0.15)
init_st7789v()
cmd(0x2A); data(bytes([0x00, 0x28, 0x00, 0xEF]))  # CASET: 40-280
cmd(0x2B); data(bytes([0x00, 0x00, 0x00, 0xEF]))  # RASET: 0-239
cmd(0x2C)
dc.set_value(1)
for row in range(240):
    for col in range(240):
        spi.writebytes([0x07, 0xE0])  # GREEN
    if row % 40 == 0:
        print(f"  GREEN row {row}/240...")
time.sleep(2)
print("  Did you see GREEN?\n")

# Test 3: With row offset
print("Test 3: With column offset 0, row offset 40...")
spi.close()
time.sleep(0.5)
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0
rst.set_value(0); time.sleep(0.01); rst.set_value(1); time.sleep(0.15)
init_st7789v()
cmd(0x2A); data(bytes([0x00, 0x00, 0x00, 0xEF]))  # CASET: 0-239
cmd(0x2B); data(bytes([0x00, 0x28, 0x00, 0xEF]))  # RASET: 40-280
cmd(0x2C)
dc.set_value(1)
for row in range(240):
    for col in range(240):
        spi.writebytes([0x00, 0x1F])  # BLUE
    if row % 40 == 0:
        print(f"  BLUE row {row}/240...")
time.sleep(2)
print("  Did you see BLUE?\n")

# Test 4: 3-wire SPI simulation (DC tied high — all data)
print("Test 4: 3-wire mode (DC tied high — all bytes as data)...")
spi.close()
time.sleep(0.5)
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0
rst.set_value(0); time.sleep(0.01); rst.set_value(1); time.sleep(0.15)
# No DC toggle — send everything as "data"
dc.set_value(1)
# Try sending init as raw bytes (this won't work but tests if panel responds to data-only)
for _ in range(100):
    spi.writebytes([0xFF, 0xFF])
time.sleep(0.5)
# Now fill WHITE
for row in range(240):
    for col in range(240):
        spi.writebytes([0xFF, 0xFF])
    if row % 40 == 0:
        print(f"  WHITE row {row}/240...")
time.sleep(2)
print("  Did you see WHITE?\n")

# Test 5: Inverted MADCTL
print("Test 5: Inverted MADCTL (0x60)...")
spi.close()
time.sleep(0.5)
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0
rst.set_value(0); time.sleep(0.01); rst.set_value(1); time.sleep(0.15)
cmd(0x01); time.sleep(0.15)
cmd(0x11); time.sleep(0.12)
cmd(0x36); data(0x60)  # MX + MADCTL invert
cmd(0x3A); data(0x55)
cmd(0xB2); data(bytes([0x0C, 0x0C, 0x00, 0x33, 0x33]))
cmd(0xB7); data(0x35)
cmd(0xBB); data(0x19)
cmd(0xC0); data(0x2C)
cmd(0xC2); data(0x01)
cmd(0xC3); data(0x12)
cmd(0xC4); data(0x20)
cmd(0xC6); data(0x0F)
cmd(0xD0); data(bytes([0xA4, 0xA1]))
cmd(0x21); time.sleep(0.01)
cmd(0x13); time.sleep(0.01)
cmd(0x29); time.sleep(0.12)
fill_color(0xF8, 0x00, "RED-inverted")
print("  Did you see RED?\n")

# Cleanup
bl.set_value(0)
dc.set_value(0)
spi.close()
print("=== All tests complete ===")
