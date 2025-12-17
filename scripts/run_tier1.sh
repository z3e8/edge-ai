#!/usr/bin/env bash
set -euo pipefail

# local run with telemetry enabled

python3 - <<'PY'
import sys
maj, minor = sys.version_info[:2]
if (maj, minor) > (3, 11):
    print("python is too new for tensorflow==2.15.0. use python 3.11 (or older).")
    raise SystemExit(1)
PY

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt

export EDGE_MODE="tier1"
export DEVICE_ID="${DEVICE_ID:-dev-001}"
export CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
export TELEMETRY_PATH="${TELEMETRY_PATH:-/telemetry}"
export DEVICE_TOKEN="${DEVICE_TOKEN:-devtoken}"
export TELEMETRY_SPOOL_DIR="${TELEMETRY_SPOOL_DIR:-./ignored/telemetry-spool}"
export MODEL_VERSION="${MODEL_VERSION:-v1}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-5000}"

python3 src/app.py

