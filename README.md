# Edge AI Inference on Raspberry Pi
Tiny Flask API that runs MobileNetV2 image classification on-device, with a bounded queue + “fail fast” overload behavior.

## Overview 
I use a MobileNetV2 model for image classification on a Raspberry Pi, exposed as a small REST API for inference requests. It includes request queueing with backpressure, structured logging, and it fails fast under load instead of slowing everything down.

I built this to get a feel for what “production-style” ML inference looks like on constrained edge hardware (not just running a model in a notebook). The goal was to understand backpressure, latency tradeoffs, and the failure modes you hit when inference can’t keep up with incoming requests.

I intentionally kept it to a single worker and a bounded queue so overload behavior stays explicit and observable.

## Live Demo Link & Screenshots
(to be added later)

## Tech Stack
- Python 3.9+
- Flask
- TensorFlow (MobileNetV2)
- Pillow + numpy
- (optional) OpenCV for webcam mode

## Key Features
- POST `/infer` takes a base64 image and returns top-5 predictions + latency
- Bounded FIFO queue (`QUEUE_SIZE`, default 10). If full -> **503** right away
- Single worker thread (so behavior is predictable on the Pi)
- `/health`, `/status`, `/metrics` endpoints for basic introspection
- Structured-ish logging + request IDs (good enough for a demo)
- Webcam mode that runs local inference every N seconds

## Setup
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 src/app.py   # default http://localhost:5000
```
Try it:
- `GET /health`
- `POST /infer` with JSON: `{"image": "<base64>"}` (see `tests/demo.py`)
Webcam mode:
```bash
pip install opencv-python
CAMERA_INTERVAL=5 python3 src/webcam_inference.py
```

## Architecture 
Basically: API enqueues work, worker does preprocess + model.predict, API waits for result. Queue is bounded so overload is obvious.
```
client -> Flask (/infer) -> bounded Queue -> worker thread -> MobileNetV2 -> result
              |-> /health /metrics /status
```

## Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                     │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP/REST
                             ▼
┌────────────────────────────────────────────────────────────┐
│                      Flask API Server                      │
│  ┌──────────────────────┐      ┌──────────────────────┐    │
│  │   Data Plane         │      │   Control Plane      │    │
│  │   /infer (POST)      │      │   /health (GET)      │    │
│  │                      │      │   /metrics (GET)     │    │
│  │                      │      │   /status (GET)      │    │
│  └──────────┬───────────┘      └──────────────────────┘    │
└─────────────┼──────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Request Queue (FIFO)                     │
│              (Bounded, In-Memory, Thread-Safe)              │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      Worker Thread                          │
│  1. Dequeue request                                         │
│  2. Preprocess image (resize to 224x224)                    │
│  3. Run inference (MobileNetV2)                             │
│  4. Return top-5 predictions                                │
│  5. Update metrics                                          │
└─────────────────────────────────────────────────────────────┘
```

## Future Improvements
- switch base64 uploads to multipart to cut overhead
- auth (even basic token) for `/infer`
- compare 1 worker vs small worker pool (throughput vs tail latency)
- better metrics (thread-safe, histograms, etc)

## Credits 
Designed and built by Zane Hensley. 
