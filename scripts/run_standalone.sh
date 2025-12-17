#!/usr/bin/env bash
set -euo pipefail

# quick local run (standalone mode)

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

export EDGE_MODE="standalone"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-5000}"

python3 src/app.py

