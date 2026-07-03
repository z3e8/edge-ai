# Edge AI Service Architecture

This document describes the implemented architecture of this repository based on code in `src/`, `scripts/`, `tests/`, and `edge-ai.service`.

## 1) System purpose and boundaries

This project is a single-process Python edge inference service that:

- Receives base64-encoded images over HTTP (`POST /infer`).
- Performs image classification using TensorFlow MobileNetV2.
- Applies explicit backpressure with a bounded in-memory queue and fail-fast `503` responses when overloaded.
- Optionally (Tier 1 mode) emits out-of-band telemetry batches to a control plane with local disk spooling when control-plane delivery fails.

It is designed for local/edge deployment (for example Raspberry Pi) and favors predictable behavior over high-throughput complexity.

## 2) Implemented runtime architecture

At runtime, the service is one Flask process with background threads:

1. **Main Flask thread**
   - Handles incoming HTTP requests (`/`, `/health`, `/status`, `/metrics`, `/infer`).
   - Validates/parses requests and enqueues inference work.
2. **Inference worker thread** (always on)
   - Consumes queue entries one at a time.
   - Runs preprocessing + model inference + prediction decoding.
   - Writes results into an in-memory result map keyed by request id.
3. **Telemetry sender thread** (only when `EDGE_MODE=tier1`)
   - Batches telemetry events from an internal queue.
   - Sends batches to control plane (`requests.post(..., timeout=3)`).
   - Spools to disk and retries later if send fails.

### High-level component map

```text
Client
  |
  v
Flask API (src/app.py)
  |- /infer -> validation/base64 decode/PIL decode -> bounded queue
  |- /health, /status, /metrics
  |
  v
Inference Worker Thread (src/app.py::worker_thread)
  -> preprocess_image (src/preprocessing.py)
  -> get_model().predict (src/model.py)
  -> decode_predictions (MobileNetV2)
  -> results[request_id]
  -> telemetry.enqueue(event)

/infer handler polls results[request_id] and returns JSON response

Tier1 only:
telemetry queue -> TelemetryClient worker (src/telemetry.py)
  -> control plane POST
  -> on failure: spool json files to disk
  -> later drain spool and resend
```

## 3) Core modules and responsibilities

### `src/app.py` (orchestration and API surface)

- Reads configuration from environment variables.
- Initializes logging via `setup_logging(...)`.
- Creates shared runtime structures:
  - bounded request queue: `queue.Queue(maxsize=QUEUE_SIZE)`
  - `results` map (`request_id -> inference result`)
  - metrics dict (`total_requests`, `requests_rejected`, `total_latency_ms`, `completed_requests`)
- Loads model at startup (`load_model()`).
- Initializes `TelemetryClient` and starts it.
- Starts single daemon inference worker.
- Registers SIGTERM/SIGINT handler for graceful-ish drain (`request_queue.join()` with 60s timeout).
- Implements all HTTP endpoints.

### `src/model.py` (model lifecycle + identity)

- Global singleton model instance (`model`).
- Model source behavior:
  - If `MODEL_PATH` is set: loads Keras model from file and computes SHA-256.
  - Else: loads `MobileNetV2(weights="imagenet")`.
- Exposes:
  - `load_model()`
  - `get_model()`
  - `get_model_identity()` -> model version, SHA-256, model path.

### `src/preprocessing.py` (input transform)

- Resizes image to `224x224`.
- Converts PIL image -> NumPy array.
- Adds batch dimension.
- Applies MobileNetV2 `preprocess_input` normalization.

### `src/telemetry.py` (Tier1 telemetry transport)

- Asynchronous best-effort telemetry subsystem.
- Uses internal event queue; never blocks inference path.
- Batches events (`batch_size`, `flush_interval_s`).
- Sends JSON payloads with optional bearer token auth.
- On send failure: writes spool files (`.json`) to `spool_dir`.
- Drains oldest spool file first on future loops (approximate ordering).
- Enforces spool cap by deleting oldest files when over `spool_max_files`.

### `src/logging_config.py` (structured logs)

- Configures root logger with JSON formatter.
- Emits fields: `timestamp`, `level`, `message`, and optional `request_id`, exception data.
- Logging itself is thread-safe through Python logging internals.

### `src/webcam_inference.py` (standalone local capture mode)

- Separate script (not integrated with HTTP service lifecycle).
- Uses OpenCV camera capture loop + same model/preprocess/decoder pipeline.
- Optional utility mode for local capture/inference testing.

## 4) HTTP API contract (implemented)

### `GET /`
- Returns: `{"message": "hello world"}`

### `GET /health`
- Healthy when model is loaded (`get_model() is not None`).
- Returns `200` + `{"status":"healthy","model_loaded":true}` in normal operation.

### `GET /status`
- Returns device/mode/model identity and runtime status:
  - `device_id`, `edge_mode`
  - `model`, `model_version`, `model_sha256`
  - `telemetry_enabled`
  - queue capacity/current depth
  - uptime + static app version

### `GET /metrics`
- Returns aggregate counters and queue depth:
  - `total_requests`
  - `requests_rejected`
  - computed `average_latency_ms`
  - telemetry counters (`batches_sent`, failures, backlog, spool files)

### `POST /infer`
- Input: JSON body containing base64 image string in `image`.
- Validation stages:
  1. JSON body required.
  2. `image` field required.
  3. Base64 decode required.
  4. PIL image decode required.
- Overload handling:
  - If queue full (or race to full): increments rejection metric and returns `503`.
- Success path:
  - Enqueue `(request_id, image, start_time)`.
  - Busy-wait poll until worker writes `results[request_id]`.
  - Return top-5 predictions + latency.

## 5) Detailed data flow

## Inference request flow

1. Client sends `POST /infer` with base64 image JSON payload.
2. API thread assigns UUID `request_id`, increments `total_requests`.
3. API thread decodes payload into PIL image.
4. API thread checks queue capacity:
   - full -> immediate `503` and telemetry overload event (`http_status=503` in Tier1).
   - available -> enqueue request.
5. Worker thread dequeues request.
6. Worker preprocesses image (`224x224`, batch dimension, normalize).
7. Worker runs model inference (`model.predict`) and decodes top-5 labels.
8. Worker computes end-to-end latency and updates completion metrics.
9. Worker stores result in shared `results` map and enqueues success telemetry event (`http_status=200` in Tier1).
10. API thread detects result and returns JSON response.

## Telemetry flow (Tier1)

1. App creates `TelemetryClient(enabled=True, ...)`.
2. `telemetry.enqueue(event)` is called from request path (success/rejection events).
3. Telemetry worker:
   - first attempts to drain existing spool files (oldest first),
   - then collects new in-memory events into a batch,
   - sends payload to control plane endpoint.
4. On send failure:
   - increments failure counter,
   - writes batch to spool directory as JSON.
5. When connectivity recovers:
   - spool files are retried and deleted on successful send.

## 6) Concurrency model and consistency notes

- **Single inference worker** means all model inference is serialized.
- Queue + worker pattern avoids concurrent model execution complexity.
- `/infer` request handlers block waiting for their own result via polling (`sleep(0.01)` loop).
- Shared maps/counters (`results`, `metrics`) are not explicitly locked:
  - acceptable for this small demo/service design,
  - can have race risk under high concurrency for exact counter precision.

## 7) Modes and deployment topology

### Standalone mode (`EDGE_MODE=standalone`)

- API + inference queue/worker only.
- Telemetry client is instantiated but disabled (`enabled=False`), so no sender thread activity.

### Tier1 mode (`EDGE_MODE=tier1`)

- All standalone behavior plus active telemetry worker.
- Requires/uses:
  - `CONTROL_PLANE_URL`
  - `TELEMETRY_PATH`
  - optional `DEVICE_TOKEN`
  - spool configuration

### Local control plane simulator

- `scripts/fake_control_plane.py` provides:
  - `POST /telemetry` receiver,
  - optional token auth check,
  - JSONL sink append for received payloads.

## 8) Startup and shutdown lifecycle

## Startup order (`src/app.py`)

1. Read env config.
2. Configure logger.
3. Initialize queue/metrics structures.
4. Load model (hard-fail process on load error).
5. Create/start telemetry client.
6. Start inference worker daemon thread.
7. Register SIGTERM/SIGINT handlers.
8. Start Flask server.

## Shutdown behavior

- On SIGTERM/SIGINT:
  - sets shutdown flag,
  - tries to drain inference queue with up to 60s timeout,
  - exits process.
- Telemetry thread is daemonized; there is no explicit flush/join on shutdown.

## 9) Configuration surface (implemented env vars)

### Core service

- `QUEUE_SIZE` (default `10`)
- `HOST` (default `0.0.0.0`)
- `PORT` (default `5000`)
- `LOG_LEVEL` (default `INFO`)

### Identity and mode

- `EDGE_MODE` (`standalone` or `tier1`, defaults to `standalone`)
- `DEVICE_ID` (default `dev-001`)

### Model

- `MODEL_PATH` (optional custom model file)
- `MODEL_VERSION` (default `unknown`)

### Telemetry (used in Tier1)

- `CONTROL_PLANE_URL` (default `http://127.0.0.1:8000`)
- `TELEMETRY_PATH` (default `/telemetry`)
- `DEVICE_TOKEN` (optional bearer token)
- `TELEMETRY_FLUSH_INTERVAL_SECONDS` (default `3`)
- `TELEMETRY_BATCH_SIZE` (default `50`)
- `TELEMETRY_SPOOL_DIR` (default `./ignored/telemetry-spool`)
- `TELEMETRY_SPOOL_MAX_FILES` (default `500`)

## 10) Operational scripts and service integration

- `scripts/run_standalone.sh`: local standalone run with venv + deps.
- `scripts/run_tier1.sh`: local Tier1 run with telemetry env.
- `scripts/demo_tier1.sh`: one-command demo that starts fake control plane + edge service, then runs demo and load test.
- `edge-ai.service`: systemd unit for Pi deployment (`Restart=always`, journal logging, environment vars).

## 11) Verification and tests present in repo

- `tests/test_basic.py`: endpoint smoke/integration checks (`/health`, `/infer`, `/metrics`).
- `tests/load_test.py`: concurrent request burst to observe 503 backpressure behavior.
- `tests/demo.py`: feature walkthrough script.
- `tests/verify_setup.py`: dependency and file presence check.

These are script-style tests/demos, not a full `pytest` suite.

## 12) What is implemented vs. documented aspirations

Implemented in code:

- Bounded queue with fail-fast overload rejection (`503`).
- Single inference worker thread.
- MobileNetV2 inference with top-5 decoded predictions.
- Health/status/metrics endpoints.
- Tier1 telemetry batching + retries via disk spooling.
- Structured JSON logging.
- Graceful queue-drain attempt on shutdown signal.

Not implemented in code (important for architecture expectations):

- Multipart upload input path (current input is base64 JSON only).
- Advanced latency percentiles/histograms (only average latency is exposed).
- Live hot model swap without restart (current model load path is startup/restart based).

