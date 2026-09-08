#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COOKBOOK_MAKEFILE="/opt/source/pru-cookbook-code/common/Makefile"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/install_pru_firmware.sh" >&2
  exit 1
fi
if [[ ! -f "$COOKBOOK_MAKEFILE" ]]; then
  echo "Missing $COOKBOOK_MAKEFILE" >&2
  echo "Install the BeagleBoard PRU cookbook/tools before loading this experiment." >&2
  exit 1
fi

for pin in P9_31 P9_29; do
  config-pin "$pin" pruout
  mode="$(config-pin -q "$pin")"
  printf '%s\n' "$mode"
  if [[ "$mode" != *"pruout"* ]]; then
    echo "Failed to place $pin in pruout mode." >&2
    exit 1
  fi
done

make -C "$EXPERIMENT_DIR/pru" TARGET=servo_pwm.pru0
echo "PRU0 firmware loaded. P9_31=head (R30 bit 0), P9_29=body (R30 bit 1)."
