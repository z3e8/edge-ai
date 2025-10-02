# Edge AI Inference on Raspberry Pi

A lightweight ML inference service for edge devices like a Raspberry Pi.

## Overview

I use a MobileNetV2 model for image classification on a Raspberry Pi, exposed as a small REST API for inference requests. It includes request queueing with backpressure, structured logging, and it fails fast under load instead of slowing everything down.

I built this to get a feel for what “production-style” ML inference looks like on constrained edge hardware (not just running a model in a notebook). The goal was to understand backpressure, latency tradeoffs, and the failure modes you hit when inference can’t keep up with incoming requests.

I intentionally kept it to a single worker and a bounded queue so overload behavior stays explicit and observable.


## Core Components

### API Endpoints

- **POST /infer** - send a base64-encoded image for classification
- **GET /health** - quick health check (returns model load status)
- **GET /metrics** - view request metrics and latency stats
- **GET /status** - view system status (uptime, queue depth, model info)

### Request Queue

- bounded FIFO queue (default size: 10)
- returns 503 immediately when the queue is full (no blocking)
- a single worker thread processes requests one at a time
- built to make backpressure behavior obvious

### Model

- pretrained MobileNetV2 (ImageNet weights)
- loaded once at startup
- CPU-only inference
- returns top-5 predictions with confidence scores

### Observability

- structured JSON logging with request IDs (so you can follow a request end-to-end)
- request latency tracking
- queue depth monitoring
- rejection metrics

### Webcam Inference Mode

Captures images from a USB webcam (default: 1 image every 5 seconds) and runs inference locally, printing the top-5 predictions.

- captures frames at configurable intervals (default: 5 seconds)
- runs inference using the same MobileNetV2 model
- prints top-5 predictions with confidence scores
- no API server required - direct model inference

## Design Decisions

- **Single worker thread**: I kept it to one worker to keep CPU usage predictable on the Pi and avoid contention inside TensorFlow. Throughput is lower, but tail latency is easier to reason about.
- **Bounded in-memory queue**: I use a bounded queue to keep backpressure explicit instead of letting latency grow unbounded.
- **503 on overload**: I chose failing fast over blocking to protect the system and make overload behavior obvious to clients.
- **CPU-only inference**: I stuck to CPU-only to match typical Raspberry Pi setups and avoid hardware-specific dependencies.


## Known Limitations

- TensorFlow startup time is noticeable on the Pi due to model load.
- Throughput is limited to one inference at a time by design.
- Base64 image upload adds overhead but simplifies client compatibility.
- Metrics are process-local and reset on restart.


## Future Improvements

- Replace base64 image uploads with multipart streaming to reduce memory overhead.
- Add simple token-based auth to protect `/infer` on shared networks.
- Experiment with a small worker pool to compare throughput vs tail latency on RP5.



## Architecture

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

## Setup Instructions

### Prerequisites

**For Raspberry Pi deployment:**
- Raspberry Pi or linux system (I used RP5 with 8GB RAM)
- Python 3.9+
- Internet connection for initial setup

**For local development/testing:**
- macOS or Linux
- Python 3.9+
- Internet connection for downloading dependencies and model

### Local Development (Mac/Linux)

If you want to try it locally before deploying to a Raspberry Pi:

1. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Run the service**
   ```bash
   python3 src/app.py
   ```
   
   Service will start on http://localhost:5001

4. **Test it** (in another terminal)
   ```bash
   source venv/bin/activate
   python3 tests/test_basic.py
   ```

5. **Run demo or load test**
   ```bash
   python3 tests/demo.py
   python3 tests/load_test.py
   ```

6. **Run webcam inference** (if webcam available)
   ```bash
   python3 src/webcam_inference.py
   ```

### Installation (Raspberry Pi)

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd edge-ai
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Download model (optional)**
   
   The model auto-downloads on first run, but you can pre-download:
   ```bash
   python3 -c "import tensorflow as tf; tf.keras.applications.MobileNetV2(weights='imagenet')"
   ```

5. **Run the service**
   ```bash
   python3 src/app.py
   ```
   
   Service will start on http://0.0.0.0:5000

6. **Test it** (in another terminal)
   ```bash
   source venv/bin/activate
   python3 tests/test_basic.py
   ```

7. **Run demo**
   ```bash
   python3 tests/demo.py
   ```

8. **Run webcam inference mode** (optional)
   ```bash
   # requires USB webcam connected
   python3 src/webcam_inference.py
   
   # custom interval (every 10 seconds)
   CAMERA_INTERVAL=10 python3 src/webcam_inference.py
   
   # use different camera (if multiple cameras)
   CAMERA_INDEX=1 python3 src/webcam_inference.py
   ```

### Installing as System Service

To run automatically on boot:

1. **Edit service file** if paths differ
   ```bash
   # check WorkingDirectory and ExecStart paths in edge-ai.service
   ```

2. **Install service**
   ```bash
   sudo cp edge-ai.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable edge-ai
   sudo systemctl start edge-ai
   ```

3. **Check status**
   ```bash
   sudo systemctl status edge-ai
   journalctl -u edge-ai -f
   ```

### Configuration

**API Server** environment variables (set in edge-ai.service or shell):

- `QUEUE_SIZE` - Max queue depth (default: 10)
- `PORT` - HTTP port (default: 5000)
- `HOST` - Bind address (default: 0.0.0.0)
- `LOG_LEVEL` - Logging level (default: INFO)

**Webcam Inference** environment variables:

- `CAMERA_INTERVAL` - Seconds between captures (default: 5)
- `CAMERA_INDEX` - Camera device index (default: 0)

