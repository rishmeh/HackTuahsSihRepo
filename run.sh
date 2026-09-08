#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting Table Tot's laptop services."
echo "The Raspberry Pi peripheral daemon must be started separately with hardware/run.sh."
exec "$SCRIPT_DIR/ml/run.sh"
