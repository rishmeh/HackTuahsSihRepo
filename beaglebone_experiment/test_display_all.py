#!/usr/bin/env python3
"""Comprehensive display test — tries multiple init sequences with full power/gamma setup."""
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

# Try different SPI modes
for mode in [0, 3]:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 40_000_000
    spi.mode = mode

    bl.set_value(1)

    # Reset
    rst.set_value(1); time.sleep(0.01)
    rst.set_value(0); time.sleep(0.01)
    rst.set_value(1); time.sleep(0.15)

    def cmd(c):
        dc.set_value(0); spi.writebytes([c])
    def data(d):
        dc.set_value(1); spi.writebytes(list(d) if isinstance(d, (bytes, bytearray)) else [d])

    print(f"\n=== Testing SPI mode {mode} ===")
    
    # Test 1: Minimal ST7789 with full power control
    print("Test 1: ST7789 with full power control...")
    cmd(0x01); time.sleep(0.15)  # SWRESET
    cmd(0x11); time.sleep(0.12)  # SLPOUT
    cmd(0x3A); data(0x55);       # COLMOD 16bit
    cmd(0x36); data(0x00);       # MADCTL
    cmd(0xB2); data(bytes([0x0C, 0x0C, 0x00, 0x33, 0x33]))  # PORCTRL
    cmd(0xB7); data(0x35)        # GCTRL
    cmd(0xBB); data(0x19)        # VCOMS
    cmd(0xC0); data(0x2C)        # LCMCTRL
    cmd(0xC2); data(0x01)        # VDVVRHEN
    cmd(0xC3); data(0x12)        # VRHS
    cmd(0xC4); data(0x20)        # VDVS
    cmd(0xC6); data(0x0F);       # FRCTRL2
    cmd(0xD0); data(bytes([0xA4, 0xA1]))  # PWCTRL1
    cmd(0xE0); data(bytes([0xD0, 0x04, 0x0D, 0x11, 0x13, 0x2B, 0x3F, 0x54, 0x4C, 0x18, 0x0D, 0x0B, 0x1F, 0x23]))  # GMCTRP1
    cmd(0xE1); data(bytes([0xD0, 0x04, 0x0C, 0x11, 0x13, 0x2C, 0x3F, 0x44, 0x51, 0x2F, 0x1F, 0x1F, 0x20, 0x23]))  # GMCTRN1
    cmd(0x21); time.sleep(0.01)  # INVON
    cmd(0x13); time.sleep(0.01)  # NORON
    cmd(0x29); time.sleep(0.12)  # DISPON

    # Fill RED
    cmd(0x2A); data(bytes([0,0,0,239]))
    cmd(0x2B); data(bytes([0,0,0,239]))
    cmd(0x2C)
    dc.set_value(1)
    for _ in range(240*240):
        spi.writebytes([0xF8, 0x00])
    
    time.sleep(2)
    bl.set_value(0)
    print("  Done. Did you see RED?")
    bl.set_value(1)

    # Test 2: ILI9341 with full power control
    print("Test 2: ILI9341 with full power control...")
    cmd(0x01); time.sleep(0.15)  # SWRESET
    cmd(0x11); time.sleep(0.12)  # SLPOUT
    cmd(0xCF); data(bytes([0x00, 0xC1, 0x30]))  # PWCTR3
    cmd(0xED); data(bytes([0x64, 0x03, 0x12, 0x81]))  # PWRSEQ
    cmd(0xE8); data(bytes([0x85, 0x00, 0x78]))  # TIMING
    cmd(0xCB); data(bytes([0x39, 0x2C, 0x00, 0x34, 0x02]))  # PWCTR1
    cmd(0xF7); data(0x20)        # PRCR
    cmd(0xEA); data(bytes([0x00, 0x00]))  # EN3G
    cmd(0xC0); data(0x23)        # PWCTR1
    cmd(0xC1); data(0x10)        # PWCTR2
    cmd(0xC5); data(bytes([0x3E, 0x28]))  # VMCTR1
    cmd(0xC7); data(0x86)        # VMCTR2
    cmd(0x36); data(0x48)        # MADCTL
    cmd(0x3A); data(0x55)        # COLMOD
    cmd(0xB1); data(bytes([0x00, 0x18]))  # FRMCTR1
    cmd(0xB6); data(bytes([0x08, 0x82, 0x27]))  # DISCTRL
    cmd(0xF2); data(0x00)        # EN3G
    cmd(0x26); data(0x01)        # GAMMASET
    cmd(0xE0); data(bytes([0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1, 0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00]))  # GAMMA+
    cmd(0xE1); data(bytes([0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1, 0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F]))  # GAMMA-
    cmd(0x11); time.sleep(0.12)  # SLPOUT
    cmd(0x29); time.sleep(0.12)  # DISPON

    # Fill GREEN
    cmd(0x2A); data(bytes([0,0,0,239]))
    cmd(0x2B); data(bytes([0,0,0,239]))
    cmd(0x2C)
    dc.set_value(1)
    for _ in range(240*240):
        spi.writebytes([0x07, 0xE0])  # GREEN in RGB565
    
    time.sleep(2)
    bl.set_value(0)
    print("  Done. Did you see GREEN?")
    bl.set_value(1)

    # Test 3: ST7735
    print("Test 3: ST7735...")
    cmd(0x01); time.sleep(0.15)  # SWRESET
    cmd(0x11); time.sleep(0.12)  # SLPOUT
    cmd(0xB1); data(bytes([0x01, 0x2C, 0x2D]))  # FRMCTR1
    cmd(0xB2); data(bytes([0x01, 0x2C, 0x2D]))  # FRMCTR2
    cmd(0xB3); data(bytes([0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D]))  # FRMCTR3
    cmd(0xB4); data(0x07)  # INVCTR
    cmd(0xC0); data(bytes([0xA2, 0x02, 0x84]))  # PWCTR1
    cmd(0xC1); data(0xC5)  # PWCTR2
    cmd(0xC2); data(bytes([0x0A, 0x00]))  # PWCTR3
    cmd(0xC3); data(bytes([0x8A, 0x2A]))  # PWCTR4
    cmd(0xC4); data(bytes([0x8A, 0xEE]))  # PWCTR5
    cmd(0xC5); data(0x0E)  # VMCTR1
    cmd(0x36); data(0xC0)  # MADCTL
    cmd(0xE0); data(bytes([0x02, 0x1C, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2D, 0x29, 0x25, 0x2B, 0x39, 0x00, 0x01, 0x03, 0x10]))  # GMCTRP1
    cmd(0xE1); data(bytes([0x03, 0x1D, 0x07, 0x06, 0x2E, 0x2C, 0x29, 0x2D, 0x2E, 0x2E, 0x37, 0x3F, 0x00, 0x00, 0x02, 0x10]))  # GMCTRN1
    cmd(0x3A); data(0x05)  # COLMOD 16bit
    cmd(0x29); time.sleep(0.12)  # DISPON

    # Fill BLUE
    cmd(0x2A); data(bytes([0,0,0,239]))
    cmd(0x2B); data(bytes([0,0,0,239]))
    cmd(0x2C)
    dc.set_value(1)
    for _ in range(240*240):
        spi.writebytes([0x00, 0x1F])  # BLUE in RGB565
    
    time.sleep(2)
    bl.set_value(0)
    print("  Done. Did you see BLUE?")

    spi.close()
    bl.set_value(0)

print("\n=== Complete ===")
print("If you saw any color, note which test number and mode.")
print("If nothing worked, the panel may need different wiring or is not responding to SPI.")
