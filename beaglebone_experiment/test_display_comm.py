#!/usr/bin/env python3
"""ST7789 communication test — reads back panel status register to verify SPI is working."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import spidev
import gpiod

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

print("=== ST7789 Communication Test ===\n")
print("This test sends commands to the panel and reads back the status register.")
print("If the panel responds, SPI is working.\n")

# Initialize GPIO
print("Initializing GPIO...")
dc_line, dc_chip = gpio_init(48, "dc")
rst_line, rst_chip = gpio_init(31, "rst")
bl_line, bl_chip = gpio_init(50, "bl")

# Backlight on
gpio_set(bl_line, 1)

# Initialize SPI
print("Initializing SPI...")
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000  # 1 MHz for reliability
spi.mode = 0b00

# Reset sequence
print("Resetting panel...")
gpio_set(rst_line, 1)
time.sleep(0.01)
gpio_set(rst_line, 0)
time.sleep(0.01)
gpio_set(rst_line, 1)
time.sleep(0.12)

def send_cmd(cmd):
    gpio_set(dc_line, 0)
    spi.writebytes([cmd & 0xFF])

def send_data(data):
    gpio_set(dc_line, 1)
    spi.writebytes(list(data) if isinstance(data, (bytes, bytearray)) else [data & 0xFF])

def read_status():
    """Read status register (0x09) — returns 5 bytes."""
    gpio_set(dc_line, 0)
    # ST7789 RDDST command
    spi.writebytes([0x09])
    gpio_set(dc_line, 1)
    # Read 5 bytes (dummy + 4 status bytes)
    result = spi.xfer2([0x00, 0x00, 0x00, 0x00, 0x00])
    return result[1:]  # Skip dummy byte

# Initialize panel
print("Sending initialization sequence...")
send_cmd(0x01); time.sleep(0.15)  # SWRESET
send_cmd(0x11); time.sleep(0.12)  # SLPOUT
send_cmd(0x3A); send_data(0x55); time.sleep(0.01)  # COLMOD
send_cmd(0x36); send_data(0x00); time.sleep(0.01)  # MADCTL
send_cmd(0x21); time.sleep(0.01)  # INVON
send_cmd(0x13); time.sleep(0.01)  # NORON
send_cmd(0x29); time.sleep(0.12)  # DISPON

# Read status
print("Reading status register...")
status = read_status()
print(f"  Status bytes: {[hex(b) for b in status]}")

# Try RDDID (0x04) — read display ID
print("Reading display ID (0x04)...")
gpio_set(dc_line, 0)
spi.writebytes([0x04])
gpio_set(dc_line, 1)
rddid = spi.xfer2([0x00, 0x00, 0x00, 0x00])
print(f"  RDDID bytes: {[hex(b) for b in rddid]}")

# Try RDID1 (0xDA), RDID2 (0xDB), RDID3 (0xDC)
print("Reading ID registers...")
for cmd, name in [(0xDA, "RDID1"), (0xDB, "RDID2"), (0xDC, "RDID3")]:
    gpio_set(dc_line, 0)
    spi.writebytes([cmd])
    gpio_set(dc_line, 1)
    result = spi.xfer2([0x00, 0x00, 0x00, 0x00])
    print(f"  {name} (0x{cmd:02X}): {[hex(b) for b in result]}")

print("\n=== Results ===")
if status and status[0] != 0xFF:
    print("  Status register responded — panel is likely alive!")
elif rddid[1] != 0xFF and rddid[1] != 0x00:
    print("  Display ID responded — panel is communicating!")
else:
    print("  No valid response — possible issues:")
    print("    1. Panel not connected properly")
    print("    2. Panel not ST7789 (could be ILI9341, ST7735, etc.)")
    print("    3. Panel is dead")
    print("    4. MISO pin not connected (needed for readback)")

# Cleanup
gpio_set(bl_line, 0)
dc_line.release()
rst_line.release()
bl_line.release()
dc_chip.close()
rst_chip.close()
bl_chip.close()
spi.close()
