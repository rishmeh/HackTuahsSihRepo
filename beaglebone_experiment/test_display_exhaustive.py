#!/usr/bin/env python3
"""ST7789V exhaustive test — tries all SPI modes, CS polarities, and init variations."""
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

print("=== ST7789V Exhaustive Test ===\n")

def run_test(mode, cs_active_high, label):
    """Run a test with specific SPI mode and CS polarity."""
    print(f"\n--- {label} ---")
    
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1_000_000
    spi.mode = mode
    
    # Set CS polarity
    if cs_active_high:
        spi.cshigh = True
    else:
        spi.cshigh = False
    
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
    cmd(0x3A); data(0x55)
    cmd(0x36); data(0x00)
    cmd(0x21)
    cmd(0x13)
    cmd(0x29); time.sleep(0.12)
    
    # Fill RED
    cmd(0x2A); data(bytes([0,0,0,239]))
    cmd(0x2B); data(bytes([0,0,0,239]))
    cmd(0x2C)
    dc.set_value(1)
    for _ in range(240*240):
        spi.writebytes([0xF8, 0x00])
    
    time.sleep(2)
    bl.set_value(0)
    dc.set_value(0)
    spi.close()
    
    print(f"  Done. Did you see RED?")
    time.sleep(1)

# Test all SPI modes
for mode in [0, 1, 2, 3]:
    run_test(mode, False, f"SPI mode {mode}, CS active low")

# Test CS active high
for mode in [0, 3]:
    run_test(mode, True, f"SPI mode {mode}, CS active high")

# Test with longer delays
print("\n--- Long delay test ---")
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1_000_000
spi.mode = 0
bl.set_value(1)
rst.set_value(1); time.sleep(0.1)
rst.set_value(0); time.sleep(0.1)
rst.set_value(1); time.sleep(0.5)  # Longer reset

def cmd(c):
    dc.set_value(0); spi.writebytes([c])
def data(d):
    dc.set_value(1); spi.writebytes(list(d) if isinstance(d, (bytes, bytearray)) else [d])

cmd(0x01); time.sleep(0.5)  # Longer sleep after reset
cmd(0x11); time.sleep(0.5)  # Longer sleep after sleep out
cmd(0x3A); data(0x55); time.sleep(0.1)
cmd(0x36); data(0x00); time.sleep(0.1)
cmd(0x21); time.sleep(0.1)
cmd(0x13); time.sleep(0.1)
cmd(0x29); time.sleep(0.5)  # Longer sleep after display on

cmd(0x2A); data(bytes([0,0,0,239]))
cmd(0x2B); data(bytes([0,0,0,239]))
cmd(0x2C)
dc.set_value(1)
for _ in range(240*240):
    spi.writebytes([0xF8, 0x00])

time.sleep(2)
bl.set_value(0)
dc.set_value(0)
spi.close()
print("  Done. Did you see RED?")

print("\n=== All tests complete ===")
