#!/usr/bin/env python3
"""ST7789V test at very slow SPI speed for debugging."""
try:
    import spidev
    import gpiod
except ImportError:
    print("This test requires spidev and gpiod (BeagleBone only).")
    raise SystemExit(0)
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

print("=== ST7789V Slow Speed Test ===\n")

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 100_000  # 100 kHz — very slow for debugging
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

# Minimal ST7789V init
print("Sending minimal init at 100kHz...")
cmd(0x01); time.sleep(0.15)
cmd(0x11); time.sleep(0.12)
cmd(0x3A); data(0x55)
cmd(0x36); data(0x00)
cmd(0x21)
cmd(0x13)
cmd(0x29); time.sleep(0.12)

# Fill RED slowly
print("Filling RED...")
cmd(0x2A); data(bytes([0,0,0,239]))
cmd(0x2B); data(bytes([0,0,0,239]))
cmd(0x2C)
dc.set_value(1)
pixel = [0xF8, 0x00]
for i in range(240*240):
    spi.writebytes(pixel)
    if i % 1000 == 0:
        print(f"  Pixel {i}/{240*240}...")

time.sleep(3)
bl.set_value(0)
dc.set_value(0)
spi.close()
print("\nDone. Did you see RED?")
