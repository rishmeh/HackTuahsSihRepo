#!/bin/bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "  Table Tot — Dual-Machine Startup"
echo "  Brain: LAPTOP | Peripherals: PI"
echo "============================================"
echo ""
echo "This script starts ONLY the ML backend on this machine."
echo "Run hardware/bridge.py on the Pi separately."
echo ""

# Activate virtual environment if it exists
if [ -d "$REPO_ROOT/.venv-laptop" ]; then
    source "$REPO_ROOT/.venv-laptop/bin/activate"
elif [ -d "$REPO_ROOT/venv" ]; then
    source "$REPO_ROOT/venv/bin/activate"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Check for .env or .env.laptop
if [ -f "$SCRIPT_DIR/.env.laptop" ]; then
    set -a
    source "$SCRIPT_DIR/.env.laptop"
    set +a
elif [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

cleanup() {
    kill "${ML_PID:-}" "${VOICE_PID:-}" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[1/2] Starting ML backend on laptop..."
cd "$SCRIPT_DIR"
uvicorn main:app --host 0.0.0.0 --port 8000 &

ML_PID=$!

for attempt in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    if [ "$attempt" -eq 40 ]; then
        echo "ERROR: ML backend did not become ready."
        exit 1
    fi
    sleep 0.5
done

echo "[2/2] Starting voice worker (laptop mic and speaker)..."
ML_API_URL="http://127.0.0.1:8000" python3 voice_agent.py &
VOICE_PID=$!

LAPTOP_IP="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
LAPTOP_IP="${LAPTOP_IP:-127.0.0.1}"

echo ""
echo "============================================"
echo "  ML Backend running on this machine"
echo "  API:      http://$LAPTOP_IP:8000"
echo "  Health:   http://$LAPTOP_IP:8000/health"
echo "  Docs:     http://$LAPTOP_IP:8000/docs"
echo "============================================"
echo ""
echo "Next: SSH into your Pi and run:"
echo "  ssh pi@<PI_IP>"
echo "  cd /home/pi/tabletot"
echo "  LAPTOP_URL=http://$LAPTOP_IP:8000 bash hardware/run.sh"
echo ""
echo "Press Ctrl+C to stop."

wait "$ML_PID" "$VOICE_PID"
