#!/usr/bin/env python3
"""ST7789V loopback test — verify SPI data is actually reaching the panel."""
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

print("=== ST7789V SPI Loopback Test ===\n")

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000  # 1 MHz for reliable loopback
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

# Init
cmd(0x01); time.sleep(0.15)
cmd(0x11); time.sleep(0.12)
cmd(0x36); data(0x00)
cmd(0x3A); data(0x55)
cmd(0x29); time.sleep(0.12)

# Read status register (0x09) — should return 5 bytes
print("Reading status register (0x09)...")
cmd(0x09)
dc.set_value(1)
result = spi.xfer2([0x00, 0x00, 0x00, 0x00, 0x00])
print(f"  Result: {[hex(b) for b in result]}")

# Read display ID (0x04)
print("Reading display ID (0x04)...")
cmd(0x04)
dc.set_value(1)
result = spi.xfer2([0x00, 0x00, 0x00, 0x00])
print(f"  Result: {[hex(b) for b in result]}")

# Read ST7789V specific registers
print("Reading ST7789V registers...")
for cmd_byte, name in [(0x0A, "POWER_MODE"), (0x0B, "MADCTL"), (0x0C, "PIXEL_FORMAT"), (0x0D, "IMAGE_MODE"), (0x0E, "SIGNAL_MODE"), (0x0F, "SELF_DIAG")]:
    cmd(cmd_byte)
    dc.set_value(1)
    result = spi.xfer2([0x00, 0x00])
    print(f"  {name} (0x{cmd_byte:02X}): {[hex(b) for b in result]}")

# Fill RED
print("\nFilling RED...")
cmd(0x2A); data(bytes([0x00, 0x00, 0x00, 0xEF]))
cmd(0x2B); data(bytes([0x00, 0x00, 0x00, 0xEF]))
cmd(0x2C)
dc.set_value(1)
for _ in range(240*240):
    spi.writebytes([0xF8, 0x00])

# Read back status
print("Reading status after fill...")
cmd(0x09)
dc.set_value(1)
result = spi.xfer2([0x00, 0x00, 0x00, 0x00, 0x00])
print(f"  Result: {[hex(b) for b in result]}")

# Try reading GRAM (0x2E)
print("Reading GRAM (0x2E)...")
cmd(0x2E)
dc.set_value(1)
result = spi.xfer2([0x00, 0x00, 0x00])
print(f"  Result: {[hex(b) for b in result]}")

# Cleanup
bl.set_value(0)
dc.set_value(0)
spi.close()

print("\n=== Summary ===")
print("If all reads return 0x00, the panel is not driving MISO.")
print("This could mean:")
print("  1. MISO pin not connected (floating)")
print("  2. Panel is write-only (some ST7789V panels don't have MISO)")
print("  3. Panel is in a state where it doesn't respond")
print("  4. SPI loopback is not working")
