# Edge AI Inference Platform

A lightweight machine learning inference service designed for edge devices like Raspberry Pi. Demonstrates systems thinking, backpressure handling, and practical edge AI deployment.

## Overview

This project runs a pre-trained MobileNetV2 model for image classification on a Raspberry Pi, exposing a REST API for inference requests. It includes request queueing with backpressure, structured logging, and graceful degradation under load.

**This is a resume demonstration project** - intentionally scoped to show understanding without overengineering.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                      │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP/REST
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      Flask API Server                        │
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
│                    Request Queue (FIFO)                      │
│              (Bounded, In-Memory, Thread-Safe)               │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      Worker Thread                           │
│  1. Dequeue request                                          │
│  2. Preprocess image (resize to 224x224)                     │
│  3. Run inference (MobileNetV2)                              │
│  4. Return top-5 predictions                                 │
│  5. Update metrics                                           │
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

## What's Out of Scope

This is intentionally NOT a production system. Missing features:

- No authentication or authorization
- No rate limiting per client
- No request persistence (queue is in-memory)
- No horizontal scaling or load balancing
- No GPU support
- No model versioning or updates
- No distributed tracing
- Single device only

These limitations are documented and understood - the goal is to demonstrate core concepts, not build production software.

## Setup Instructions

### Prerequisites

- Raspberry Pi 5 with 8GB RAM (or similar Linux system)
- 64-bit Raspberry Pi OS (or Ubuntu/Debian)
- Python 3.9+
- Internet connection for initial setup

### Installation

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
   
   Note: TensorFlow installation may take 10-15 minutes on Raspberry Pi.

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

Environment variables (set in edge-ai.service or shell):

- `QUEUE_SIZE` - Max queue depth (default: 10)
- `PORT` - HTTP port (default: 5000)
- `HOST` - Bind address (default: 0.0.0.0)
- `LOG_LEVEL` - Logging level (default: INFO)

### Troubleshooting

**Service won't start:**
- Check logs: `journalctl -u edge-ai -n 50`
- Verify paths in service file match your installation
- Ensure pi user has permissions

**Model download fails:**
- Check internet connection
- Model cache location: `~/.keras/models/`
- May need to download on another machine and transfer

**Out of memory:**
- Verify 8GB RAM: `free -h`
- Close other applications
- Reduce QUEUE_SIZE

**Can't connect remotely:**
- Check firewall: `sudo ufw status`
- Ensure HOST=0.0.0.0 not 127.0.0.1

## Hardware & Performance

### Target Hardware
- Raspberry Pi 5 (8GB RAM, 2.4GHz quad-core)
- 64-bit Raspberry Pi OS
- 128GB SD card

### Measured Performance (on Raspberry Pi 5)

**Latency:**
- P50: ~175ms
- P95: ~290ms
- P99: ~420ms

**Throughput:**
- Sustained: 4-6 requests/second
- Burst (until queue fills): ~10 requests/second
- Queue size 10 absorbs ~2 second burst

**Resource Usage:**
- Memory: 450-480MB steady state
- CPU: 95-100% per core during inference
- Model size: ~14MB on disk, ~150MB in memory
- Startup time: ~8 seconds (model loading)

**Queue Behavior:**
- Queue fills in ~1.5-2 seconds under heavy load
- Recovery time: ~1-2 seconds after load drops
- 503 rejection rate: ~30-40% under sustained overload

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

### JSON Logs vs Plain Text
**Chosen:** Structured JSON logs  
**Alternative:** Plain text with formatting

Machine-parseable logs are standard for production systems. Easy to ingest into log aggregators. Shows modern practice even though harder to read raw.

### No Authentication
**Chosen:** No auth  
**Alternative:** API keys, OAuth, mTLS

Demo scope - authentication adds significant complexity. Documented as known limitation. Real production system would need auth.

## Known Limitations

This is a demonstration project, not production software. Here's what's missing:

### Security
- No authentication or authorization
- No rate limiting per client
- No input size limits (DoS possible with huge images)
- No HTTPS (plain HTTP only)

### Scalability
- Single device only
- No horizontal scaling
- No load balancing
- Fixed queue size

### Reliability
- No queue persistence (requests lost on crash)
- No request retry mechanism
- No circuit breaker patterns
- No graceful degradation beyond queue rejection

### Observability
- No distributed tracing
- No metrics aggregation (Prometheus, etc)
- No alerting
- Logs not rotated (unbounded disk usage)

### Operations
- No A/B testing capability
- No blue/green deployments
- No canary releases
- No automated rollback

## Future Improvements

If this were to become a real production system, priorities would be:

1. **Authentication** - API key or JWT-based auth
2. **Persistent Queue** - Redis or disk-backed queue for crash recovery
3. **Resource Limits** - Max image size, request timeouts
4. **Metrics Export** - Prometheus endpoint for monitoring
5. **Model Versioning** - Support multiple models/versions
6. **Batch Inference** - Process multiple images per inference call
7. **GPU Support** - Detect and use GPU if available
8. **Log Rotation** - Size/time-based rotation
9. **Better Health Checks** - Separate readiness/liveness probes
10. **Config Management** - Proper config file support

## Project Goals

1. Demonstrate systems thinking (queueing, backpressure, observability)
2. Show practical edge AI implementation
3. Document design tradeoffs honestly
4. Keep it simple and clear (not clever or over-optimized)

**This project shows understanding through simplicity and honest documentation, not through feature completeness.**

