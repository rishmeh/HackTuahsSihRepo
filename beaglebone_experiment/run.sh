#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.bbb"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root because PRU shared RAM is mapped through /dev/mem:" >&2
  echo "  sudo bash run.sh" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Create $ENV_FILE from .env.bbb.example and set LAPTOP_URL." >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${LAPTOP_URL:?Set LAPTOP_URL in .env.bbb}"
exec python3 "$SCRIPT_DIR/bridge.py"
