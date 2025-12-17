#!/usr/bin/env bash
set -euo pipefail

# one-command demo for tier1 mode

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

cleanup() {
  if [ -n "${EDGE_PID:-}" ]; then
    kill "${EDGE_PID}" >/dev/null 2>&1 || true
  fi
  if [ -n "${CP_PID:-}" ]; then
    kill "${CP_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

export CONTROL_PLANE_PORT="${CONTROL_PLANE_PORT:-8000}"
export CONTROL_PLANE_TOKEN="${CONTROL_PLANE_TOKEN:-devtoken}"
export TELEMETRY_SINK_PATH="${TELEMETRY_SINK_PATH:-./ignored/telemetry-recv.jsonl}"

python3 scripts/fake_control_plane.py >/dev/null 2>&1 &
CP_PID=$!

export EDGE_MODE="tier1"
export DEVICE_ID="${DEVICE_ID:-dev-001}"
export DEVICE_TOKEN="${DEVICE_TOKEN:-$CONTROL_PLANE_TOKEN}"
export CONTROL_PLANE_URL="http://127.0.0.1:${CONTROL_PLANE_PORT}"
export TELEMETRY_SPOOL_DIR="${TELEMETRY_SPOOL_DIR:-./ignored/telemetry-spool}"
export MODEL_VERSION="${MODEL_VERSION:-v1}"
export HOST="127.0.0.1"
export PORT="${PORT:-5000}"

python3 src/app.py >/dev/null 2>&1 &
EDGE_PID=$!

sleep 2

python3 tests/demo.py
python3 tests/load_test.py

echo
echo "done. telemetry saved to ${TELEMETRY_SINK_PATH}"

