#!/bin/bash
set -uo pipefail

echo "============================================"
echo "  Table Tot — Pi Camera/Display/Servo Bridge"
echo "============================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"

if [ -d "$REPO_ROOT/.venv-pi" ]; then
    source "$REPO_ROOT/.venv-pi/bin/activate"
fi

# Load .env.pi if present
if [ -f "$SCRIPT_DIR/.env.pi" ]; then
    set -a
    source "$SCRIPT_DIR/.env.pi"
    set +a
fi

# LAPTOP_URL defaults to mDNS (tabletot-laptop.local:8000).
# Only set it explicitly if mDNS doesn't work on your network.
LAPTOP_URL="${LAPTOP_URL:-http://tabletot-laptop.local:8000}"

echo "Brain (laptop): $LAPTOP_URL"
echo "Camera type:    ${CAMERA_TYPE:-usb}"
echo "Starting camera upload, face display and servo command polling..."
echo ""

cd "$SCRIPT_DIR"
exec python3 bridge.py
