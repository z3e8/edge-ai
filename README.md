# Edge AI Inference on Raspberry Pi
Tiny Flask service for on-device image classification with a bounded queue + fail-fast overload.

## Description
This is a small edge inference server I run on a Pi. It takes a base64 image, runs MobileNetV2, and returns top-5 predictions. Main thing I cared about was making overload behavior obvious (bounded queue + 503 instead of slow timeouts).

Also has an optional `EDGE_MODE=tier1` that exports telemetry batches to a local “control plane” receiver. 

## Live Demo Link & Screenshots

## Tech Stack
- Python 3.9–3.11 (tensorflow 2.15)
- Flask + requests
- TensorFlow (MobileNetV2), Pillow, numpy

## Features
- `POST /infer` returns top-5 + latency
- bounded FIFO queue (`QUEUE_SIZE`, default 10). queue full → 503 right away
- single worker thread (simple + predictable)
- `/health`, `/status`, `/metrics`
- tier1 mode: telemetry batches + disk spool if control plane is down

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 src/app.py
python3 tests/demo.py
```

Tier1 local demo (starts fake control plane + edge + runs demo + load burst):

```bash
./scripts/demo_tier1.sh
```

## Architecture

```text
client -> Flask (/infer) -> bounded queue -> worker -> model -> response
              |-> /health /status /metrics
              |-> telemetry sender thread (tier1 only)
```

## Future Improvements
- switch base64 to multipart uploads
- better metrics (percentiles, not just averages)
- a safer model swap flow (right now it’s restart-based)

## Challenges and What I Learned
- bounded queues are nice because failure is explicit. it’s way easier to debug “503, queue full” than random long tail latency.
- telemetry can’t be on the request path. even “just one post” can hang your service if the network is weird.
- disk spooling is a cheap way to make edge stuff feel real. but you need a cap or you’ll fill storage.

## Credits
solo project built by Zane Hensley
