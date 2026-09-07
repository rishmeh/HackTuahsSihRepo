#!/usr/bin/env python3
"""ST7789 hardware diagnostic — no face rendering, just raw SPI + GPIO test.
Uses gpiod v1 API (compatible with python3-libgpiod 1.6.x on Debian 12)."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import spidev
import gpiod

# GPIO setup using v1 API
def gpio_init(gpio_num, consumer="test"):
    bank = gpio_num // 32
    line = gpio_num % 32
    chip_name = f"gpiochip{bank}"
    chip_path = f"/dev/{chip_name}"
    if not os.path.exists(chip_path):
        for i in range(4):
            if os.path.exists(f"/dev/gpiochip{i}"):
                chip_name = f"gpiochip{i}"
                break
    try:
        chip = gpiod.Chip(chip_name)
        line_obj = chip.get_line(line)
        line_obj.request(consumer=consumer, type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
        return line_obj, chip
    except Exception as e:
        print(f"  GPIO {gpio_num} init failed: {e}")
        return None, None

def gpio_set(line_obj, val):
    if line_obj:
        try:
            line_obj.set_value(val)
        except Exception as e:
            print(f"  GPIO set error: {e}")

# Initialize SPI
print("=== ST7789 Hardware Diagnostic ===\n")

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0b00

# GPIO pins
DC_GPIO = 48   # P9_15
RST_GPIO = 31  # P9_13
BL_GPIO = 50   # P9_14

print("Initializing GPIO...")
dc_line, dc_chip = gpio_init(DC_GPIO, "dc")
rst_line, rst_chip = gpio_init(RST_GPIO, "rst")
bl_line, bl_chip = gpio_init(BL_GPIO, "bl")

if not dc_line:
    print("FAIL: Cannot init DC GPIO")
    sys.exit(1)

def send_cmd(cmd):
    gpio_set(dc_line, 0)
    spi.writebytes([cmd & 0xFF])

def send_data(data):
    gpio_set(dc_line, 1)
    spi.writebytes(list(data) if isinstance(data, (bytes, bytearray)) else [data & 0xFF])

# Hardware reset
print("Resetting panel...")
gpio_set(rst_line, 1)
time.sleep(0.01)
gpio_set(rst_line, 0)
time.sleep(0.01)
gpio_set(rst_line, 1)
time.sleep(0.12)

# Backlight on
print("Backlight ON")
gpio_set(bl_line, 1)

# Initialize panel
print("Initializing ST7789...")
send_cmd(0x01); time.sleep(0.15)  # SWRESET
send_cmd(0x11); time.sleep(0.12)  # SLPOUT
send_cmd(0x3A); send_data(0x55); time.sleep(0.01)  # COLMOD 16bit
send_cmd(0x36); send_data(0x00); time.sleep(0.01)  # MADCTL
send_cmd(0x21); time.sleep(0.01)  # INVON
send_cmd(0x13); time.sleep(0.01)  # NORON
send_cmd(0x29); time.sleep(0.12)  # DISPON

print("Panel initialized. Now filling with solid colors...\n")

def fill_screen(r, g, b):
    """Fill entire 240x240 with solid RGB color."""
    # CASET
    send_cmd(0x2A)
    send_data(bytes([0x00, 0x00, 0x00, 0xEF]))  # 0-239
    # RASET
    send_cmd(0x2B)
    send_data(bytes([0x00, 0x00, 0x00, 0xEF]))  # 0-239
    # RAMWR
    send_cmd(0x2C)
    gpio_set(dc_line, 1)
    # RGB565
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    high = (rgb565 >> 8) & 0xFF
    low = rgb565 & 0xFF
    pixel = bytes([high, low])
    # Send 240*240 pixels
    buf = pixel * (240 * 240)
    # Send in chunks
    chunk_size = 4096
    for i in range(0, len(buf), chunk_size):
        spi.writebytes(list(buf[i:i+chunk_size]))

colors = [
    ("RED", 255, 0, 0),
    ("GREEN", 0, 255, 0),
    ("BLUE", 0, 0, 255),
    ("WHITE", 255, 255, 255),
    ("YELLOW", 255, 255, 0),
    ("CYAN", 0, 255, 255),
    ("MAGENTA", 255, 0, 255),
    ("OFF (BLACK)", 0, 0, 0),
]

for name, r, g, b in colors:
    print(f"  Fill: {name} — look at display")
    fill_screen(r, g, b)
    time.sleep(3)

print("\nDone. Did you see any colors?")
print("  If RED/GREEN/BLUE were all the same (white/gray/black), wiring may be wrong.")
print("  If nothing at all, panel may be dead or wrong type (not ST7789).")
print("  If colors appeared, panel works — issue is in face rendering code.")

# Cleanup
gpio_set(bl_line, 0)
dc_line.release()
rst_line.release()
bl_line.release()
dc_chip.close()
rst_chip.close()
bl_chip.close()
spi.close()
