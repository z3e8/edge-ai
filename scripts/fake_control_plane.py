#!/usr/bin/env python3
"""tiny local receiver for telemetry batches"""

import json
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request


app = Flask(__name__)

CONTROL_PLANE_TOKEN = os.getenv("CONTROL_PLANE_TOKEN", "").strip() or None
SINK_PATH = os.getenv("TELEMETRY_SINK_PATH", "./ignored/telemetry-recv.jsonl").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _auth_ok() -> bool:
    if not CONTROL_PLANE_TOKEN:
        return True
    h = request.headers.get("authorization", "")
    return h == f"Bearer {CONTROL_PLANE_TOKEN}"


def _append_sink(obj: dict):
    # write jsonl so it's easy to grep later
    d = os.path.dirname(SINK_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(SINK_PATH, "a") as f:
        f.write(json.dumps(obj) + "\n")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": _now()})


@app.route("/telemetry", methods=["POST"])
def telemetry():
    if not _auth_ok():
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    device_id = payload.get("device_id")
    model_version = payload.get("model_version")
    events = payload.get("events") or []

    # just print something useful and keep a local copy
    try:
        print(f"[telemetry] device={device_id} model={model_version} events={len(events)}")
    except Exception:
        pass

    try:
        _append_sink(payload)
    except Exception as e:
        return jsonify({"error": f"sink write failed: {e}"}), 500

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("CONTROL_PLANE_PORT", "8000"))
    app.run(host="0.0.0.0", port=port)

