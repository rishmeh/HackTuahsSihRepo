# Table Tot — BeagleBone Black SPI Display Setup Log

> **September 2026** | **Status: Display stays black (backlight ON, no image)**

---

## Project Context

### What is Table Tot?

Table Tot is an **AI-powered desk companion robot for students**, built for Smart India Hackathon 2026 (Problem Statement SIH26224). The robot lives on a student's study desk, learns their routine, and builds personalised productivity workflows.

**Hardware platform:**
- Raspberry Pi 5 (primary) OR BeagleBone Black (this experiment)
- Camera, mic, speaker, servos, animated face display
- PIR sensor for presence detection

**Software stack:**
- Offline-first AI with on-device SLM (Qwen via llama.cpp)
- Moonshine STT (speech-to-text)
- Kokoro TTS (text-to-speech)
- Parent dashboard: React + Vite web app over local WiFi

### System Architecture

The robot uses a **dual-machine architecture**:

```
┌─────────────────────────────┐       HTTP :8000      ┌─────────────────────────────┐
│         LAPTOP (Brain)       │ ◄────────────────────► │   BEAGLEBONE BLACK (IO)     │
│                              │                        │                              │
│  ┌────────────────────────┐  │   JPEG frames          │  ┌────────────────────────┐  │
│  │  ml/main.py (FastAPI)  │  │ ◄────────────────────  │  │  bridge.py             │  │
│  │  Face recognition      │  │                        │  │  USB camera (OpenCV)   │  │
│  │  Voice/TTS             │  │   JSON commands        │  └────────────────────────┘  │
│  │  Chat/SLM              │  │ ─────────────────────► │  ┌────────────────────────┐  │
│  │  Learner profiling     │  │                        │  │  spi_display.py        │  │
│  └────────────────────────┘  │                        │  │  ST7789 SPI display    │  │
│                              │                        │  └────────────────────────┘  │
│                              │                        │  ┌────────────────────────┐  │
│                              │                        │  │  PRU0 servo firmware   │  │
│                              │                        │  │  Head = P9_31 (bit 0)  │  │
│                              │                        │  │  Body = P9_29 (bit 1)  │  │
│                              │                        │  └────────────────────────┘  │
└─────────────────────────────┘                        └─────────────────────────────┘
```

**The laptop is the brain.** The BBB is just a peripheral bridge — it captures camera frames, renders face emotions on the display, and moves servos. All AI inference (face recognition, voice, chat) runs on the laptop.

### What This Experiment Does

The `beaglebone_experiment/` folder makes a **BeagleBone Black Rev C** act as:
1. USB camera capture (sends 640×480 JPEG to laptop ~2 fps)
2. ST7789 SPI IPS face display (receives face state from laptop, renders emotions)
3. Two-servo control via PRU0 (head + body MG90S servos)

### Hardware Components

| Component | Connection |
|-----------|-----------|
| **ST7789 240×240 SPI IPS display** | SPI0: P9_17 (CS), P9_18 (MOSI), P9_22 (SCLK) + 3 GPIO |
| **USB webcam** | BBB USB-A host port |
| **Head MG90S servo** | P9_31 (PRU0 R30 bit 0) |
| **Body MG90S servo** | P9_29 (PRU0 R30 bit 1) |
| **Ethernet** | BBB RJ45 → same LAN as laptop |
| **Power** | 5V barrel jack (recommended for camera/display use) |

### BBB Pin Map (Used Pins)

```
BBB P9 Header — Used Pins
═══════════════════════════════════════════════════════
Pin    │ Function          │ Notes
═══════╪═══════════════════╪═══════════════════════════
P9_1   │ GND               │ Common ground
P9_3   │ 3.3V              │ Display VCC
P9_13  │ GPIO 31 (output)  │ Display RES/RST
P9_14  │ GPIO 50 (output)  │ Display BL/LED (backlight)
P9_15  │ GPIO 48 (output)  │ Display DC/RS
P9_17  │ SPI0_CS0          │ Display CS
P9_18  │ SPI0_D1 (MOSI)    │ Display SDA/MOSI
P9_22  │ SPI0_SCLK         │ Display SCL/SCK
P9_29  │ PRU0 R30 bit 1    │ Body servo signal
P9_31  │ PRU0 R30 bit 0    │ Head servo signal
═══════╧═══════════════════╧═══════════════════════════
```

**Constraints:**
- P9_29/P9_31 are EXCLUSIVELY PRU0 outputs (PWM servo timing)
- SPI0 pins (P9_17/18/21/22) are EXCLUSIVELY for ST7789 display
- P9_12 (GPIO 60) is reserved by HDMI overlay
- HDMI overlay is DISABLED (to free SPI0 pins)
- eMMC is active (uses some GPIOs)

### Software Files

| File | Purpose |
|------|---------|
| `beaglebone_experiment/bridge.py` | Main entry point — camera + display + servo bridge |
| `beaglebone_experiment/spi_display.py` | ST7789 SPI driver + Pillow face renderer |
| `beaglebone_experiment/pru_servo.py` | PRU0 servo pulse writer (shared RAM) |
| `beaglebone_experiment/pru/servo_pwm.pru0.c` | PRU0 firmware (20ms PWM frame) |
| `beaglebone_experiment/test_spi_display.py` | Standalone display test |
| `beaglebone_experiment/test_display_configs.py` | Offset/MADCTL variation tests |
| `beaglebone_experiment/test_display_hardware.py` | Hardware diagnostic (solid colors) |
| `beaglebone_experiment/test_display_pins.py` | Pin-by-pin diagnostic |
| `beaglebone_experiment/test_display_comm.py` | SPI communication test (reads panel status) |
| `beaglebone_experiment/test_pru_servo.py` | Standalone servo test |
| `beaglebone_experiment/scripts/setup_spi_display.sh` | SPI pin config + overlay loader |
| `beaglebone_experiment/scripts/install_pru_firmware.sh` | PRU firmware compiler + loader |
| `beaglebone_experiment/.env.bbb.example` | Configuration template |
| `beaglebone_experiment/README.md` | Wiring docs + bring-up sequence |

### Face Renderer Architecture

`spi_display.py` uses **Pillow** (not Pygame) to render animated faces on the 240×240 ST7789 panel:

- **States:** `idle`, `listening`, `speaking`, `thinking`, `happy`, `sleeping`, `focus`
- **Animations:** blink cycle, mouth open/close, eyebrow expressions
- **Display protocol:** 4-wire SPI (CS, DC, SCLK, MOSI) + hardware RST + GPIO DC
- **Color format:** RGB565 (16-bit) — converted from Pillow RGB at flush time
- **Frame rate:** ~30 FPS target
- **Threading:** animation runs in background thread, thread-safe `set_state()` from bridge

---

## Setup Issues Log

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

## Problem 5: GPIO 48 (P9_15) ALSO Invalid — ROOT CAUSE FOUND (SOLVED)

**Symptom:** Same error after switching to P9_15 (GPIO 48):
```
export_store: invalid GPIO 48
OSError: [Errno 22] Invalid argument
```

**Initial Theory:** GPIO 48 might be reserved by eMMC. **This was a red herring** — eMMC uses P8 header pins (mmc1_dat*), not GPMC address lines.

**Root Cause (identified by Claude):** The **legacy sysfs GPIO interface** (`/sys/class/gpio`) is deprecated and unreliable on kernel 6.12. It's not that GPIO 48 is specifically blocked — it's that the sysfs shim is inconsistent on modern device trees. Some pins (like RST on P9_13/GPIO31 and BL on P9_14/GPIO50) happen to work, while others (like DC on P9_15/GPIO48) don't.

**Fix:** Replace sysfs GPIO with **libgpiod** (the chardev API). Added `GpioLine` class in `spi_display.py` that:
1. Automatically detects the correct gpiochip for a GPIO number
2. Supports both gpiod v1 and v2 APIs
3. Holds the line open for process lifetime (no release/re-acquire per transaction)

**Files changed:**
- `spi_display.py` — replaced all `_gpio_sysfs_write()` calls with `GpioLine` class
- `scripts/setup_spi_display.sh` — added `python3-libgpiod` to dependency install

**Install on BBB:**
```bash
sudo apt install python3-libgpiod
```

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

## Problem 7: Display Stays Black (Backlight ON) — UNRESOLVED

**Symptom:** Display shows slight light (backlight ON) but no image appears. Face rendering test cycles through states but display remains black. Color fill test also shows nothing.

**What's working:**
- SPI device exists (`/dev/spidev0.0`, `/dev/spidev0.1`)
- spidev module loaded and bound
- GPIO control working via libgpiod (gpiod v1 API)
- Backlight turns on/off
- No errors in Python or kernel logs
- Panel status register responds (all zeros = no error for ST7789)

**What's NOT working:**
- No image appears on display
- Color fill test (solid RED/GREEN/BLUE/WHITE) shows nothing
- Face rendering test shows nothing
- ILI9341 init sequence — no image
- ST7735 init sequence — no image
- SPI mode 0 — no image
- SPI mode 3 — no image

**Init Sequences Tried:**
1. ❌ ST7789 minimal (SWRESET, SLPOUT, COLMOD, MADCTL, INVON, NORON, DISPON)
2. ❌ ST7789 with full power/gamma (PORCTRL, GCTRL, VCOMS, LCMCTRL, VRHS, etc.)
3. ❌ ILI9341 with full power/gamma (PWCTR1-3, PWRSEQ, VMCTR1-2, GAMMA+/-)
4. ❌ ST7735 with full power/gamma (FRMCTR1-3, INVCTR, PWCTR1-5, VMCTR1, GMCTRP1/RN1)
5. ❌ All sequences with both SPI mode 0 and mode 3

**Possible Causes:**
1. **Wrong panel type** — panel may not be ST7789, ILI9341, or ST7735. Could be:
   - GC9A01 (240×240 round, different protocol)
   - ST7789V (variant with different init)
   - ILI9340/ILI9342 (variants)
   - Custom/unknown controller
   
2. **Wrong wiring** — MOSI/MISO swapped, CS wrong, DC not connected properly

3. **Panel not receiving data correctly** — SCK not toggling, MOSI stuck high/low

4. **Panel is dead** — hardware failure

**Diagnostic Steps Taken:**
1. ✅ Tested libgpiod GPIO — all pins toggle
2. ✅ Tested SPI device — opens without error
3. ✅ Read panel status register — responds (all zeros)
4. ❌ Color fill test — display stays black
5. ❌ Face rendering test — display stays black
6. ❌ ILI9341 init — display stays black
7. ❌ ST7735 init — display stays black
8. ❌ SPI mode 0 and 3 — display stays black

**Next Diagnostic Steps:**
1. **Check panel markings** — look for IC markings on the panel PCB
2. **Try different wiring** — swap MOSI/SCK, try different CS pin
3. **Try GC9A01 init** — if panel is round, it's likely GC9A01
4. **Check if panel needs 3.3V or 5V logic** — some panels need 3.3V, some 5V
5. **Try slower SPI speed** — 1 MHz instead of 40 MHz

**Diagnostic Commands to Run:**
```bash
# Test all init sequences
cd ~/HackTuahsSihRepo/beaglebone_experiment
sudo python3 test_display_all.py
```

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
Panel DC/RS → P9_15 (GPIO 48)
Panel CS    → P9_17 (SPI0_CS0)
Panel BL    → P9_14 (GPIO 50)
```

---

## Next Steps

1. **Run `test_display_pins.py`** — verify each pin toggles with multimeter/LED
2. **Run `test_display_comm.py`** — read panel status registers to confirm communication
3. **Check panel markings** — look at the PCB for IC markings (ST7789, ILI9341, ST7735, etc.)
4. **If panel is not ST7789** — rewrite init sequence for correct controller
5. **If SPI not working** — check MOSI/SCK with multimeter, verify wiring
6. **Permanent spidev binding** — create systemd service or udev rule

---

## Files Modified

| File | Change |
|------|--------|
| `beaglebone_experiment/spi_display.py` | DC_GPIO: 60 → 48, replaced sysfs with libgpiod GpioLine class |
| `beaglebone_experiment/scripts/setup_spi_display.sh` | Rewrote for modern kernels, added python3-libgpiod |
| `beaglebone_experiment/test_spi_display.py` | Fixed sys.path for standalone use |
| `beaglebone_experiment/test_display_configs.py` | Test offset/MADCTL variations |
| `beaglebone_experiment/test_display_hardware.py` | Solid color fill test |
| `beaglebone_experiment/test_display_pins.py` | Pin-by-pin diagnostic |
| `beaglebone_experiment/test_display_comm.py` | SPI communication test (reads panel status) |
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
7. eMMC on BBB reserves many GPIOs in the GPIO1 bank (32-63) — avoid these for DC/RS.
8. libgpiod (chardev API) is the correct way to control GPIO on kernel 6.12+.
9. Black screen with backlight = panel powered but not receiving valid data.
10. Always verify panel type (ST7789 vs ILI9341 vs ST7735) before writing driver.
