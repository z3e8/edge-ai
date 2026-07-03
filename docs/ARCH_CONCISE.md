# Edge AI Architecture (Concise)

## Purpose
- Edge image-classification service with explicit overload handling.
- Input: base64 image over HTTP.
- Output: top-5 MobileNetV2 predictions + latency.
- Optional Tier1 mode sends telemetry to a control plane.

## Runtime Design
- Single Python process (`src/app.py`) with Flask.
- One bounded in-memory queue (`queue.Queue(maxsize=QUEUE_SIZE)`).
- One inference worker thread (serial inference).
- One telemetry worker thread only when `EDGE_MODE=tier1`.

## Core Components
- `src/app.py`
  - HTTP routes: `/`, `/health`, `/status`, `/metrics`, `/infer`.
  - Request validation + enqueue + wait for worker result.
  - In-memory metrics counters and queue depth reporting.
  - Signal handler attempts queue drain on shutdown.
- `src/model.py`
  - Loads model once at startup.
  - Uses `MODEL_PATH` custom model if set, else `MobileNetV2(weights="imagenet")`.
  - Exposes model identity (`model_version`, `model_sha256`, `model_path`).
- `src/preprocessing.py`
  - Resize to `224x224`, convert to numpy, add batch dim, MobileNetV2 preprocess.
- `src/telemetry.py`
  - Async telemetry queue + batch sender.
  - Sends with optional bearer token.
  - On failure, writes spool files; later drains/retries.
  - Enforces max spool file count.
- `src/logging_config.py`
  - JSON logs (`timestamp`, `level`, `message`, optional `request_id`).

## `/infer` Data Flow
1. Generate `request_id`, increment `total_requests`.
2. Validate JSON body and `image` field.
3. Base64 decode, then PIL decode.
4. If queue full: increment rejection counter, return `503`.
5. Else enqueue `(request_id, image, start_time)`.
6. Worker dequeues and preprocesses image.
7. Worker runs `model.predict(...)` and decodes top-5 classes.
8. Worker computes latency, updates metrics, stores `results[request_id]`.
9. API handler polls until result exists, then returns JSON.

## Overload/Backpressure Behavior
- Backpressure is explicit: bounded FIFO queue + fail-fast `503`.
- No unbounded buffering.
- Race case (`queue.Full` after pre-check) is also handled as `503`.

## Telemetry Flow (Tier1)
1. API/worker enqueue events (success and overload).
2. Telemetry thread batches events (`flush_interval`, `batch_size`).
3. Sends to `CONTROL_PLANE_URL + TELEMETRY_PATH`.
4. If send fails, batch is spooled to disk.
5. On recovery, spool files are sent first, then deleted on success.

## API Surface (Implemented)
- `GET /` -> hello message.
- `GET /health` -> model loaded status (`200` or `503`).
- `GET /status` -> device/mode/model identity, queue, uptime, app version.
- `GET /metrics` -> request counts, avg latency, queue depth, telemetry counters.
- `POST /infer` -> top-5 predictions + latency or validation/overload error.

## Concurrency and Consistency Notes
- Inference execution is serialized by single worker.
- Request handlers wait via short polling loop (`sleep(0.01)`).
- `metrics` and `results` are shared dicts without explicit locks.
- Design is intentionally simple; counters may be slightly non-exact under heavy concurrency.

## Modes
- `EDGE_MODE=standalone`
  - Inference service only; telemetry disabled.
- `EDGE_MODE=tier1`
  - Inference service + telemetry sender + spool/retry path.

## Main Configuration
- Core: `QUEUE_SIZE`, `HOST`, `PORT`, `LOG_LEVEL`.
- Mode/identity: `EDGE_MODE`, `DEVICE_ID`.
- Model: `MODEL_PATH`, `MODEL_VERSION`.
- Telemetry: `CONTROL_PLANE_URL`, `TELEMETRY_PATH`, `DEVICE_TOKEN`,
  `TELEMETRY_FLUSH_INTERVAL_SECONDS`, `TELEMETRY_BATCH_SIZE`,
  `TELEMETRY_SPOOL_DIR`, `TELEMETRY_SPOOL_MAX_FILES`.

## Deployment and Ops
- `scripts/run_standalone.sh` -> local standalone run.
- `scripts/run_tier1.sh` -> local Tier1 run.
- `scripts/demo_tier1.sh` -> starts fake control plane + edge service + demo/load scripts.
- `scripts/fake_control_plane.py` -> local telemetry receiver and JSONL sink.
- `edge-ai.service` -> systemd unit for Raspberry Pi deployment.

## Included Verification Scripts
- `tests/test_basic.py` -> health/infer/metrics checks.
- `tests/load_test.py` -> concurrent load to trigger queue rejection.
- `tests/demo.py` -> end-to-end feature demo.
- `tests/verify_setup.py` -> dependency + file structure verification.

## Explicit Non-Features (Current State)
- No multipart upload API (base64 JSON only).
- No percentile/histogram latency metrics (average only).
- No hot model swap workflow (model changes are restart-based).

