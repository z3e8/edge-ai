# Edge AI Inference on Raspberry Pi

Lightweight ML inference designed for edge devices like Raspberry Pi. 

## Overview

I use MobileNetV2 model for image classification on a Raspberry Pi, exposing a REST API for inference requests. Includes request queueing with backpressure, structured logging, and graceful degradation under load.

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

## Core Components

### API Endpoints

- **POST /infer** - Submit base64-encoded image for classification
- **GET /health** - Health check (returns model load status)
- **GET /metrics** - Request metrics and latency stats
- **GET /status** - System status (uptime, queue depth, model info)

### Request Queue

- Bounded FIFO queue (default size: 10)
- Immediate 503 rejection when full (no blocking)
- Single worker thread processes requests sequentially
- Demonstrates backpressure handling

### Model

- Pre-trained MobileNetV2 (ImageNet weights)
- Loaded once at startup
- CPU-only inference
- Returns top-5 predictions with confidence scores

### Observability

- Structured JSON logging with request IDs
- Request latency tracking
- Queue depth monitoring
- Rejection metrics

### Webcam Inference Mode

A standalone script that captures images from a USB webcam and runs inference locally without the API server. Useful for continuous monitoring or demo purposes.

- Captures frames at configurable intervals (default: 5 seconds)
- Runs inference using the same MobileNetV2 model
- Prints top-5 predictions with confidence scores
- No API server required - direct model inference

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

You can test the project locally before deploying to Raspberry Pi:

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

## Design Decisions & Tradeoffs

### Flask vs FastAPI
**Chosen:** Flask  
**Alternative:** FastAPI

Flask is simpler and more mature. No async/await needed since inference is CPU-bound, not I/O-bound. FastAPI has better docs and modern features, but adds complexity we don't need for this scope.

### Single Thread vs Multiprocessing
**Chosen:** Single worker thread  
**Alternative:** Multiprocessing pool

Inference is CPU-bound on a single core anyway. The GIL doesn't hurt much since TensorFlow runs in C++. Single thread is simpler for state management and matches hardware constraints.

### queue.Queue vs Redis
**Chosen:** In-memory queue.Queue  
**Alternative:** External queue (Redis)

No external dependencies needed. Python's queue.Queue is thread-safe by default and sufficient for single-process demo. Trade persistence and distributed support for simplicity.

### Immediate Rejection vs Blocking
**Chosen:** Immediate 503 when queue full  
**Alternative:** Block with timeout or return 202 Accepted

Gives client more control to implement their own retry logic. Clearer failure mode. Prevents confusion from timeouts. More honest about capacity limits.

### MobileNetV2 vs Larger Models
**Chosen:** MobileNetV2  
**Alternative:** ResNet, EfficientNet, custom model

MobileNetV2 is designed for mobile/edge devices. Good accuracy/size tradeoff (~14MB). Well-supported in TensorFlow. Pre-trained on ImageNet for common use cases.

## Future Improvements 

- auth
- rate limiting 
- request persistence (queue is in-memory)
- horizontal scaling or load balancing
- GPU support
- model versioning or updates
- distributed tracing
- multiple devices
