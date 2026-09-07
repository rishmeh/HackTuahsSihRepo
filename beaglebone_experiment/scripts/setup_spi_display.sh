#!/usr/bin/env bash
# beaglebone_experiment/scripts/setup_spi_display.sh
# Configure BBB pins for the ST7789 SPI IPS display and load the SPI0 overlay.
#
# Works with modern BeagleBone Debian (5.x/6.x kernels) where config-pin overlay
# entries may not exist. Uses U-Boot overlay loading via uEnv.txt.
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

SPI_DEV="/dev/spidev0.0"
OVERLAY="BB-SPIDEV0-00A0"

# --- Check if SPI device already exists ---
if [[ -e "${SPI_DEV}" ]]; then
  echo "SPI device already available: ${SPI_DEV}"
  echo "Skipping overlay setup."
else
  echo "SPI device not found. Checking for overlay loading..."

  # Try modern config-pin with overlay support (some newer images still support this)
  if command -v config-pin &>/dev/null; then
    echo "Trying config-pin overlay load..."
    config-pin overlay spi0 2>/dev/null || true
    config-pin overlay ${OVERLAY} 2>/dev/null || true
    sleep 1
  fi

  # Check again
  if [[ ! -e "${SPI_DEV}" ]]; then
    # Find uEnv.txt location
    UENV=""
    for path in /boot/firmware/uEnv.txt /boot/uEnv.txt; do
      if [[ -f "$path" ]]; then
        UENV="$path"
        break
      fi
    done

    if [[ -z "$UENV" ]]; then
      echo ""
      echo "ERROR: Could not find uEnv.txt. Manual overlay setup required."
      echo "Add to your boot configuration:"
      echo "  uboot_overlay_addr4=/lib/firmware/${OVERLAY}.dtbo"
      echo ""
      echo "Then reboot: sudo reboot"
      exit 1
    fi

    echo ""
    echo "Adding SPI0 overlay to ${UENV}..."

    # Check if overlay already in uEnv.txt
    if grep -q "${OVERLAY}" "$UENV" 2>/dev/null; then
      echo "Overlay already referenced in ${UENV}."
    else
      echo "# Table Tot ST7789 SPI display" >> "$UENV"
      echo "uboot_overlay_addr4=/lib/firmware/${OVERLAY}.dtbo" >> "$UENV"
      echo "Added: uboot_overlay_addr4=/lib/firmware/${OVERLAY}.dtbo"
    fi

    # Verify the overlay file exists in /lib/firmware
    if [[ ! -f "/lib/firmware/${OVERLAY}.dtbo" ]]; then
      echo ""
      echo "WARNING: /lib/firmware/${OVERLAY}.dtbo not found."
      echo "You may need to install it or check the correct overlay name."
      echo "Available SPI overlays in /lib/firmware:"
      ls /lib/firmware/BB-SPIDEV* 2>/dev/null || echo "  (none found)"
      echo ""
      echo "Trying alternative overlay names..."
      for alt in BB-SPIDEV0-00A0 BB-SPIDEV0 bbspi0; do
        if [[ -f "/lib/firmware/${alt}.dtbo" ]]; then
          echo "Found: ${alt}.dtbo"
          sed -i "s|${OVERLAY}|${alt}|g" "$UENV"
          break
        fi
      done
    fi

    echo ""
    echo "Overlay configuration added. A REBOOT is required."
    echo ""
    echo "Run: sudo reboot"
    echo ""
    echo "After reboot, run this script again to verify, then:"
    echo "  sudo python3 ${EXPERIMENT_DIR}/test_spi_display.py"
    exit 0
  fi
fi

echo ""
echo "SPI device confirmed: ${SPI_DEV}"

# --- Verify pins are configured correctly ---
echo ""
echo "Verifying pin configuration..."
if command -v config-pin &>/dev/null; then
  for pin_mode in "P9_17:spi_cs" "P9_18:spi" "P9_22:spi_sclk" "P9_15:gpio" "P9_13:gpio" "P9_14:gpio"; do
    pin="${pin_mode%%:*}"
    mode="${pin_mode##*:}"
    actual="$(config-pin -q "$pin" 2>/dev/null | head -1 || echo 'unknown')"
    echo "  $pin: $actual"
  done
else
  echo "  config-pin not available — pins configured via device tree overlay."
fi

# --- Install Python deps if missing ---
echo ""
echo "Checking Python dependencies..."
python3 -c "import spidev" 2>/dev/null || {
  echo "  Installing python3-spidev..."
  apt-get update -qq && apt-get install -y -qq python3-spidev
}
python3 -c "from PIL import Image" 2>/dev/null || {
  echo "  Installing python3-pil..."
  apt-get update -qq && apt-get install -y -qq python3-pil
}
python3 -c "import gpiod" 2>/dev/null || {
  echo "  Installing python3-libgpiod..."
  apt-get update -qq && apt-get install -y -qq python3-libgpiod
}

echo ""
echo "=== SPI display setup complete ==="
echo ""
echo "Run the test:"
echo "  cd ${EXPERIMENT_DIR}"
echo "  sudo python3 test_spi_display.py"
echo ""
echo "Then start the bridge:"
echo "  sudo bash ${EXPERIMENT_DIR}/run.sh"
