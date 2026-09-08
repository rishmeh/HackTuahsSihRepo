#!/usr/bin/env python3
"""ST7789V display test — 240x240 4-wire SPI."""
import spidev
import gpiod
import time

def gpio_init(n):
    bank, line = n // 32, n % 32
    chip = gpiod.Chip(f"gpiochip{bank}")
    l = chip.get_line(line)
    l.request(consumer="test", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
    return l, chip

dc, _ = gpio_init(48)
rst, _ = gpio_init(31)
bl, _ = gpio_init(50)

print("=== ST7789V Test ===\n")

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0

bl.set_value(1)

# Reset
rst.set_value(1); time.sleep(0.01)
rst.set_value(0); time.sleep(0.01)
rst.set_value(1); time.sleep(0.15)

def cmd(c):
    dc.set_value(0); spi.writebytes([c])
def data(d):
    dc.set_value(1); spi.writebytes(list(d) if isinstance(d, (bytes, bytearray)) else [d])

# ST7789V init sequence
print("Sending ST7789V init...")
cmd(0x01); time.sleep(0.15)  # SWRESET
cmd(0x11); time.sleep(0.12)  # SLPOUT
cmd(0x36); data(0x00)        # MADCTL (normal orientation)
cmd(0x3A); data(0x55)        # COLMOD (16-bit RGB)
cmd(0xB2); data(bytes([0x0C, 0x0C, 0x00, 0x33, 0x33]))  # PORCTRL (porch control)
cmd(0xB7); data(0x35)        # GCTRL (Gate control)
cmd(0xBB); data(0x19)        # VCOMS (VCOM setting)
cmd(0xC0); data(0x2C)        # LCMCTRL (LCM control)
cmd(0xC2); data(0x01)        # VDVVRHEN (VDV/VRH enable)
cmd(0xC3); data(0x12)        # VRHS (VRH set)
cmd(0xC4); data(0x20)        # VDVS (VDV set)
cmd(0xC6); data(0x0F)        # FRCTRL2 (frame rate control)
cmd(0xD0); data(bytes([0xA4, 0xA1]))  # PWCTRL1 (power control)
# Positive gamma
cmd(0xE0); data(bytes([0xD0, 0x04, 0x0D, 0x11, 0x13, 0x2B, 0x3F, 0x54, 0x4C, 0x18, 0x0D, 0x0B, 0x1F, 0x23]))
# Negative gamma
cmd(0xE1); data(bytes([0xD0, 0x04, 0x0C, 0x11, 0x13, 0x2C, 0x3F, 0x44, 0x51, 0x2F, 0x1F, 0x1F, 0x20, 0x23]))
cmd(0x21); time.sleep(0.01)  # INVON (display inversion on)
cmd(0x13); time.sleep(0.01)  # NORON (partial mode off)
cmd(0x29); time.sleep(0.12)  # DISPON (display on)

print("Init complete. Filling RED...\n")

# Set address window
cmd(0x2A); data(bytes([0x00, 0x00, 0x00, 0xEF]))  # CASET: 0-239
cmd(0x2B); data(bytes([0x00, 0x00, 0x00, 0xEF]))  # RASET: 0-239
cmd(0x2C)  # RAMWR

dc.set_value(1)

# Send RED pixels (RGB565: 0xF800)
pixel = [0xF8, 0x00]
for row in range(240):
    for col in range(240):
        spi.writebytes(pixel)
    if row % 40 == 0:
        print(f"  Row {row}/240...")

print("\nDone! Did you see RED?")
time.sleep(3)

# Cleanup
bl.set_value(0)
dc.set_value(0)
spi.close()
