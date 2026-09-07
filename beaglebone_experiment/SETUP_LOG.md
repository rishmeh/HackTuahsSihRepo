# Table Tot — BeagleBone Black SPI Display Setup Log

## Date: September 2026

---

## Problem 1: Repository Access (SOLVED)

**Symptom:** `git clone` fails with `403 Write access to repository not granted`.

**Cause:** User `AaKaShhhhhhhhh` tried to clone private repo owned by `rishmeh`. Personal Access Token (PAT) had insufficient scope.

**Fix:** User generated a new PAT with `repo` scope. Clone succeeded.

---

## Problem 2: Wrong uEnv.txt File (SOLVED)

**Symptom:** SPI overlay not loading despite setup script reporting success.

**Cause:** BBB has TWO uEnv.txt files:
- `/boot/uEnv.txt` — read by bootloader
- `/boot/firmware/uEnv.txt` — written by our setup script (wrong one!)

**Evidence:**
```
ls -la /boot/uEnv.txt /boot/firmware/uEnv.txt
-rw-r--r-- 1 debian debian 263 Aug 29 20:37 /boot/uEnv.txt
-rwxr-xr-x 1 debian debian 342 Sep  7 19:37 /boot/firmware/uEnv.txt
```

**Fix:** Manually added to `/boot/uEnv.txt`:
```
uboot_overlay_addr4=/lib/firmware/BB-SPIDEV0-00A0.dtbo
```

---

## Problem 3: HDMI Overlay Conflict (SOLVED)

**Symptom:** U-Boot loads both `BB-SPIDEV0-00A0.dtbo` AND `BB-HDMI-TDA998x-00A0.dtbo` — they share pins, HDMI wins, SPI device doesn't appear.

**Evidence from boot log:**
```
uboot_overlays: loading /lib/firmware/BB-SPIDEV0-00A0.dtbo ...
uboot_overlays: loading /boot/dtbs/6.12.28-bone25/BB-HDMI-TDA998x-00A0.dtbo ...
```

**Fix:** Added to `/boot/uEnv.txt`:
```
disable_uboot_overlay_hdmi=1
```

---

## Problem 4: GPIO 60 (P9_12) HDMI Conflict (SOLVED)

**Symptom:** `export_store: invalid GPIO 60` / `OSError: [Errno 22] Invalid argument`

**Cause:** P9_12 = GPIO 60 is used by HDMI on BeagleBone Black. Cannot export it while HDMI overlay is active (or even after, if the pin is reserved).

**Fix:** Changed DC/RS control pin from P9_12 to P9_15 (GPIO 48):
- `DEFAULT_DC_GPIO = 60` → `DEFAULT_DC_GPIO = 48` in `spi_display.py`
- Wiring: DC/RS → P9_15 instead of P9_12

---

## Problem 5: GPIO 48 (P9_15) ALSO Invalid (UNSOLVED)

**Symptom:** Same error after switching to P9_15 (GPIO 48):
```
export_store: invalid GPIO 48
OSError: [Errno 22] Invalid argument
```

**Status:** This is the CURRENT blocker. GPIO 48 is also reserved by something (possibly the SPI overlay itself or the universal DTB).

---

## Problem 6: SPI Device Nodes Missing (PARTIALLY SOLVED)

**Symptom:** `/dev/spidev*` not found even after overlay loaded.

**Cause:** spidev module loaded but devices not bound to driver automatically on kernel 6.12.

**Current Workaround (manual, lost on reboot):**
```bash
sudo modprobe spidev
echo spidev | sudo tee /sys/bus/spi/devices/spi0.0/driver_override
echo spi0.0 | sudo tee /sys/bus/spi/drivers/spidev/bind
```

**Proposed Permanent Fix:** Add a udev rule or systemd service to bind spidev at boot.

---

## Current BBB State

### uEnv.txt (`/boot/uEnv.txt`)
```
uname_r=6.12.28-bone25
enable_uboot_overlays=1
enable_uboot_cape_universal=0
cmdline=coherent_pool=1M net.ifnames=0 lpj=1990656 rng_core.default_quality=100 root=/dev/mmcblk1p3 ro rootfstype=ext4 rootwait
uenvcmd=mw.l 0x44E10990 0x05
uenvcmd=mw.l 0x44E10994 0x05
uboot_overlay_addr4=/lib/firmware/BB-SPIDEV0-00A0.dtbo
disable_uboot_overlay_hdmi=1
```

### Kernel
```
6.12.28-bone25
```

### Wiring
```
Panel VCC   → P9_3 (3.3V)
Panel GND   → P9_1
Panel SCK   → P9_22 (SPI0_SCLK)
Panel MOSI  → P9_18 (SPI0_D1)
Panel RST   → P9_13 (GPIO 31)
Panel DC/RS → P9_15 (GPIO 48) ← CAUSES ERROR
Panel CS    → P9_17 (SPI0_CS0)
Panel BL    → P9_14 (GPIO 50) or tie to VCC
```

---

## Next Steps

1. **Identify which GPIO pins are free on BBB** — need to check which pins are NOT reserved by HDMI, eMMC, SPI, or PRU overlays.

2. **Check if eMMC is using GPIO 48** — eMMC on BBB uses a lot of GPIOs. If so, P9_15 won't work either.

3. **Alternative approach:** Use the SPI overlay's built-in control pins and avoid GPIO sysfs entirely. Some ST7789 panels can work with hardware DC control via SPI mode3 or a separate GPIO that's confirmed free.

4. **Permanent spidev binding:** Create systemd service or udev rule to bind spidev driver at boot.

---

## Files Modified

| File | Change |
|------|--------|
| `beaglebone_experiment/spi_display.py` | DC_GPIO: 60 → 48 (P9_12 → P9_15) |
| `beaglebone_experiment/scripts/setup_spi_display.sh` | Rewrote for modern kernels, check correct uEnv.txt |
| `beaglebone_experiment/test_spi_display.py` | Fixed sys.path for standalone use |
| `beaglebone_experiment/README.md` | Updated wiring tables |
| `beaglebone_experiment/.env.bbb.example` | Added DISPLAY_DC_GPIO=48 |

---

## Lessons Learned

1. BBB has TWO uEnv.txt files — only `/boot/uEnv.txt` is read by bootloader.
2. HDMI overlay MUST be disabled for SPI0 to work (pin conflict).
3. GPIO sysfs export fails silently if pin is reserved by another overlay.
4. Kernel 6.12 requires manual spidev binding (driver_override + bind).
5. Always check `dmesg | grep -i gpio` after failed export.
6. Always check `grep spidev /proc/devices` after `modprobe spidev`.
