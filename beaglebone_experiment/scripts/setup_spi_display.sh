#!/usr/bin/env bash
# beaglebone_experiment/scripts/setup_spi_display.sh
# Configure BBB pins for the ST7789 SPI IPS display and load the SPI0 overlay.
#
# Must run as root. Does NOT touch P9_29 / P9_31 (PRU servo pins).
#
# Usage: sudo bash scripts/setup_spi_display.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/setup_spi_display.sh" >&2
  exit 1
fi

echo "=== Table Tot BBB — SPI display setup ==="

# --- Load the SPI0 device-tree overlay ---
# The overlay enables SPI0 on P9_17 (CS0), P9_18 (MOSI), P9_21 (MISO), P9_22 (SCLK).
# On modern BeagleBoard Debian images this is done via /boot/firmware/uEnv.txt or
# the cape manager. We try both approaches.

OVERLAY="BB-SPIDEV0-00A0"
SPI_DEV="/dev/spidev0.0"

# Try loading via config-pin overlay mechanism (newer images)
if command -v config-pin &>/dev/null; then
  echo "Configuring SPI0 pins via config-pin..."
  config-pin P9_17 spi_cs   || echo "  (P9_17 already in spi_cs mode or unavailable)"
  config-pin P9_18 spi     || echo "  (P9_18 already in spi mode or unavailable)"
  config-pin P9_21 spi     || echo "  (P9_21 already in spi mode or unavailable)"
  config-pin P9_22 spi_sclk || echo "  (P9_22 already in spi_sclk mode or unavailable)"
fi

# Configure GPIO control pins (DC, RST, BL) as gpio
if command -v config-pin &>/dev/null; then
  echo "Configuring GPIO control pins..."
  config-pin P9_12 gpio || echo "  (P9_12 already gpio or unavailable)"
  config-pin P9_13 gpio || echo "  (P9_13 already gpio or unavailable)"
  config-pin P9_14 gpio || echo "  (P9_14 already gpio or unavailable)"
fi

# --- Verify /dev/spidev0.0 exists ---
if [[ ! -e "${SPI_DEV}" ]]; then
  echo ""
  echo "WARNING: ${SPI_DEV} not found. You may need to reboot after loading the overlay."
  echo "Add this line to /boot/firmware/uEnv.txt (or /boot/uEnv.txt on older images):"
  echo "  uboot_overlay_addr4=/lib/firmware/${OVERLAY}.dtbo"
  echo ""
  echo "Then reboot: sudo reboot"
  echo ""
  echo "Alternatively, if using an older image, add to /boot/uEnv.txt:"
  echo "  cape_enable=bone_capemgr.enable_partno=${OVERLAY}"
  exit 1
fi

echo "SPI device found: ${SPI_DEV}"

# --- Install Python deps if missing ---
echo "Checking Python dependencies..."
python3 -c "import spidev" 2>/dev/null || {
  echo "  Installing python3-spidev..."
  apt-get update -qq && apt-get install -y -qq python3-spidev
}
python3 -c "from PIL import Image" 2>/dev/null || {
  echo "  Installing python3-pil..."
  apt-get update -qq && apt-get install -y -qq python3-pil
}

echo ""
echo "=== SPI display setup complete ==="
echo "Run the test: sudo python3 ${EXPERIMENT_DIR}/test_spi_display.py"
echo "Then start the bridge: sudo bash ${EXPERIMENT_DIR}/run.sh"
