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

# Check for .env.pi
if [ -f "$SCRIPT_DIR/.env.pi" ]; then
    set -a
    source "$SCRIPT_DIR/.env.pi"
    set +a
fi

# Default laptop URL — MUST be overridden
if [ -z "${LAPTOP_URL:-}" ]; then
    echo "ERROR: LAPTOP_URL not set. Set it with:"
    echo "  export LAPTOP_URL=http://<LAPTOP_IP>:8000"
    echo ""
    echo "Then run: python3 hardware/bridge.py"
    exit 1
fi

echo "Brain (laptop): $LAPTOP_URL"
echo "Starting camera upload, face display and servo command polling..."
echo ""

cd "$SCRIPT_DIR"
exec python3 bridge.py
