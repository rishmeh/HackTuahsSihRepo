#!/usr/bin/env python3
"""Test ILI9341 init sequence — fills screen with RED."""
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
bl.set_value(1)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 40_000_000
spi.mode = 0

# Reset
rst.set_value(1); time.sleep(0.01)
rst.set_value(0); time.sleep(0.01)
rst.set_value(1); time.sleep(0.12)

def cmd(c):
    dc.set_value(0); spi.writebytes([c])

def data(d):
    dc.set_value(1); spi.writebytes(list(d) if isinstance(d, (bytes, bytearray)) else [d])

# ILI9341 init
print("Sending ILI9341 init sequence...")
cmd(0x01); time.sleep(0.1)   # SWRESET
cmd(0x11); time.sleep(0.1)   # SLPOUT
cmd(0x3A); data(0x55)        # PIXEL FORMAT 16bit
cmd(0x36); data(0x00)        # MEMORY ACCESS CONTROL
cmd(0x29); time.sleep(0.1)   # DISPLAY ON

# Fill RED
print("Filling screen RED...")
cmd(0x2A); data(bytes([0,0,0,239]))  # CASET
cmd(0x2B); data(bytes([0,0,0,239]))  # RASET
cmd(0x2C)                             # RAMWR
dc.set_value(1)
pixel = [0xF8, 0x00]  # RED in RGB565
for _ in range(240*240):
    spi.writebytes(pixel)

time.sleep(3)
bl.set_value(0)
print("Did you see RED?")
