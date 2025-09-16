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

## Quick Start

See setup instructions below for full details.

```bash
# install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# run service
python3 src/app.py

# test it (in another terminal)
python3 tests/test_basic.py

# run demo
python3 tests/demo.py
```

## Hardware Target

- Raspberry Pi 5 (8GB RAM)
- 64-bit Raspberry Pi OS
- Expected performance:
  - Latency: 100-300ms per inference
  - Throughput: 3-10 requests/second
  - Memory: ~400-500MB

## Technology Choices

- **Flask** - Simple, mature, sufficient for demo scope
- **queue.Queue** - Thread-safe, no external deps, good for single-process
- **MobileNetV2** - Designed for edge/mobile, good accuracy/size tradeoff
- **Single worker thread** - Matches CPU-bound workload, simpler than multiprocessing
- **JSON logging** - Structured, machine-parseable, production-ready pattern

## Project Goals

1. Demonstrate systems thinking (queueing, backpressure, observability)
2. Show practical edge AI implementation
3. Document design tradeoffs honestly
4. Keep it simple and clear (not clever or over-optimized)

