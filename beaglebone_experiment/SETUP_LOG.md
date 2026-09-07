# Table Tot — BeagleBone Black SPI Display Setup Log

> **September 2026** | **Status: BLOCKED on GPIO 48 (P9_15) export error**

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
P9_15  │ GPIO 48 (output)  │ Display DC/RS ← BLOCKED
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
- P9_15 (GPIO 48) appears to also be reserved — **CURRENT BLOCKER**
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

## Problem 5: GPIO 48 (P9_15) ALSO Invalid (UNSOLVED — CURRENT BLOCKER)

**Symptom:** Same error after switching to P9_15 (GPIO 48):
```
export_store: invalid GPIO 48
OSError: [Errno 22] Invalid argument
```

**Status:** This is the CURRENT blocker. GPIO 48 is also reserved by something (possibly eMMC, SPI overlay, or the universal DTB).

**Hypothesis:** On BeagleBone Black with eMMC, many GPIOs in the GPIO1 bank (GPIO 32-63) are reserved for eMMC communication. P9_15 = GPIO1_16 = GPIO 48 may be one of these.

**What we need to find:** A GPIO pin that is:
1. NOT in HDMI overlay (P9_12, P9_14 area)
2. NOT in SPI0 overlay (P9_17, P9_18, P9_22)
3. NOT in PRU servo pins (P9_29, P9_31)
4. NOT in eMMC control lines
5. Accessible via `/sys/class/gpio/export` on kernel 6.12

**Potential free pins on BBB P9 header:**
- P9_11 (GPIO 30) — UART4_RXD, may be free
- P9_12 (GPIO 60) — HDMI, blocked
- P9_13 (GPIO 31) — currently used for RST
- P9_14 (GPIO 50) — currently used for BL
- P9_15 (GPIO 48) — eMMC, blocked
- P9_16 (GPIO 51) — eMMC, likely blocked
- P9_23 (GPIO 49) — may be free
- P9_24 (GPIO 15) — UART4_TXD, may be free
- P9_25 (GPIO 117) — eMMC, likely blocked
- P9_26 (GPIO 14) — UART4_RTS, may be free
- P9_27 (GPIO 115) — may be free
- P9_28 (GPIO 113) — SPI1_CS0, may be free

**Note:** RST (P9_13, GPIO 31) and BL (P9_14, GPIO 50) are currently working. The issue is specifically with DC/RS.

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
Panel RST   → P9_13 (GPIO 31) ← WORKS
Panel DC/RS → P9_15 (GPIO 48) ← BLOCKED
Panel CS    → P9_17 (SPI0_CS0)
Panel BL    → P9_14 (GPIO 50) ← WORKS
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
7. eMMC on BBB reserves many GPIOs in the GPIO1 bank (32-63) — avoid these for DC/RS.
